import asyncio

import pytest

from app.errors import AppError
from app.services.collection_service import CollectionService
from tests.fakes import FakeCollector, memory_repository
from tests.helpers import FakeClock, make_logger, make_post

pytestmark = pytest.mark.anyio


@pytest.fixture
def setup():
    clock = FakeClock()
    collector = FakeCollector()
    db, repository = memory_repository(clock)
    service = CollectionService(
        repository=repository,
        collector=collector,
        clock=clock,
        max_posts=25,
        ttl_seconds=60,
        logger=make_logger(),
    )
    yield service, collector, clock, db
    db.close()


def runs(db, status):
    return db.execute('SELECT COUNT(*) FROM collections WHERE status = ?', (status,)).fetchone()[0]


async def test_collects_live_stores_the_run_and_returns_what_was_stored(setup):
    service, collector, _, db = setup
    response = await service.collect('r/Ubisoft', force=False)

    assert collector.calls == [('ubisoft', 25)]
    assert (response.collection.term, response.collection.source) == ('ubisoft', 'live')
    assert sorted(p.id for p in response.posts) == ['t3_a', 't3_b']
    assert runs(db, 'success') == 1


async def test_an_invalid_term_is_rejected_before_reddit_or_the_database(setup):
    service, collector, _, db = setup
    with pytest.raises(AppError) as raised:
        await service.collect('bad name!', force=False)
    assert raised.value.code == 'INVALID_TERM'
    assert collector.calls == []
    assert runs(db, 'failed') == 0


async def test_a_fresh_collection_is_served_from_the_cache(setup):
    service, collector, clock, _ = setup
    await service.collect('ubisoft', force=False)
    clock.advance(30)

    response = await service.collect('ubisoft', force=False)

    assert len(collector.calls) == 1
    assert response.collection.source == 'cache'
    assert len(response.posts) == 2


async def test_an_old_collection_or_force_collects_live_again(setup):
    service, collector, clock, _ = setup
    await service.collect('ubisoft', force=False)
    assert (await service.collect('ubisoft', force=True)).collection.source == 'live'
    clock.advance(61)
    assert (await service.collect('ubisoft', force=False)).collection.source == 'live'
    assert len(collector.calls) == 3


async def test_concurrent_requests_for_one_term_share_one_collection(setup):
    service, collector, _, _ = setup
    collector.hold()
    first = asyncio.create_task(service.collect('ubisoft', force=False))
    second = asyncio.create_task(service.collect('r/ubisoft', force=True))
    await asyncio.sleep(0)
    collector.release()

    a, b = await asyncio.gather(first, second)

    assert len(collector.calls) == 1
    assert a.collection.id == b.collection.id


async def test_a_cancelled_waiter_does_not_cancel_the_shared_collection(setup):
    service, collector, _, _ = setup
    collector.hold()
    first = asyncio.create_task(service.collect('ubisoft', force=False))
    second = asyncio.create_task(service.collect('ubisoft', force=False))
    await asyncio.sleep(0)
    first.cancel()
    collector.release()

    assert (await second).collection.source == 'live'


async def test_different_terms_are_collected_independently(setup):
    service, collector, _, _ = setup
    await asyncio.gather(service.collect('ubisoft', False), service.collect('gaming', False))
    assert sorted(call[0] for call in collector.calls) == ['gaming', 'ubisoft']


async def test_a_collector_failure_is_recorded_and_reraised(setup):
    service, collector, _, db = setup
    collector.result = AppError('UPSTREAM_TIMEOUT')

    with pytest.raises(AppError) as raised:
        await service.collect('ubisoft', force=False)

    assert raised.value.code == 'UPSTREAM_TIMEOUT'
    row = db.execute("SELECT error_code FROM collections WHERE status='failed'").fetchone()
    assert row[0] == 'UPSTREAM_TIMEOUT'


async def test_an_unexpected_exception_becomes_internal(setup):
    service, collector, _, db = setup
    collector.result = TypeError('boom')
    with pytest.raises(AppError) as raised:
        await service.collect('ubisoft', force=False)
    assert raised.value.code == 'INTERNAL'
    assert runs(db, 'failed') == 1


async def test_a_failed_database_write_is_db_error_not_success(setup):
    service, collector, _, db = setup
    collector.result = [make_post('t3_bad', comment_count=-1)]
    with pytest.raises(AppError) as raised:
        await service.collect('ubisoft', force=False)
    assert raised.value.code == 'DB_ERROR'
    assert (runs(db, 'success'), runs(db, 'failed')) == (0, 1)


async def test_zero_posts_is_a_successful_empty_collection(setup):
    service, collector, _, _ = setup
    collector.result = []
    response = await service.collect('quiet', force=False)
    assert (response.collection.post_count, response.posts) == (0, [])


async def test_last_good_returns_the_previous_feed_as_cache(setup):
    service, _, _, db = setup
    assert service.last_good('ubisoft') is None
    assert service.last_good('bad name!') is None
    await service.collect('ubisoft', force=False)

    last = service.last_good('r/UBISOFT')

    assert (last.collection.source, last.collection.term) == ('cache', 'ubisoft')
    db.close()
    assert service.last_good('ubisoft') is None


async def test_get_posts_reads_the_database_only(setup):
    service, collector, clock, _ = setup
    assert service.get_posts('ubisoft').model_dump() == {'collection': None, 'posts': []}
    await service.collect('ubisoft', force=False)
    clock.advance(3600)

    response = service.get_posts('ubisoft')

    assert response.collection.source == 'cache'
    assert len(response.posts) == 2
    assert len(collector.calls) == 1
    with pytest.raises(AppError):
        service.get_posts('r/')


async def test_a_collector_error_keeps_its_original_cause_for_the_logs(setup):
    service, collector, _, _ = setup
    network = ConnectionResetError('socket closed')
    collector.result = AppError('UPSTREAM_ERROR', cause=network)

    with pytest.raises(AppError) as raised:
        await service.collect('ubisoft', force=False)

    assert raised.value.__cause__ is network
