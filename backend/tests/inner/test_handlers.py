import asyncio
import gc
import time

import pytest

from app.config import load_config
from app.errors import AppError
from app.inner.handlers import CollectionFailed, HealthHandler, PostsHandler
from app.inner.loop_thread import LoopThread
from app.services.collection_service import CollectionService
from tests.fakes import FakeCollector, memory_repository
from tests.helpers import FakeClock, make_logger, make_normalizer


@pytest.fixture
def loop():
    loop = LoopThread()
    yield loop
    loop.stop()


@pytest.fixture
def parts(loop):
    clock = FakeClock()
    collector = FakeCollector()
    db, repository = memory_repository(clock)
    service = CollectionService(
        repository=repository,
        collector=collector,
        normalizer=make_normalizer(),
        clock=clock,
        max_posts=25,
        ttl_seconds=60,
        logger=make_logger(),
    )
    yield service, collector, repository
    db.close()


def posts_handler(parts, loop, timeout=5.0):
    return PostsHandler(parts[0], loop, timeout)


def test_auto_collects_then_serves_the_cache(parts, loop):
    handler = posts_handler(parts, loop)
    first = handler.get({'term': 'ubisoft'})
    second = handler.get({'term': 'ubisoft'})
    assert (first['collection']['source'], second['collection']['source']) == ('live', 'cache')
    assert len(parts[1].calls) == 1


def test_live_always_collects(parts, loop):
    handler = posts_handler(parts, loop)
    handler.get({'term': 'ubisoft', 'freshness': 'live'})
    handler.get({'term': 'ubisoft', 'freshness': 'live'})
    assert len(parts[1].calls) == 2


def test_stored_never_collects(parts, loop):
    reply = posts_handler(parts, loop).get({'term': 'ubisoft', 'freshness': 'stored'})
    assert reply == {'collection': None, 'posts': []}
    assert parts[1].calls == []


def test_unknown_freshness_is_invalid_request(parts, loop):
    with pytest.raises(AppError) as raised:
        posts_handler(parts, loop).get({'term': 'ubisoft', 'freshness': 'soon'})
    assert raised.value.code == 'INVALID_REQUEST'


def test_a_failure_carries_the_last_good_feed(parts, loop):
    handler = posts_handler(parts, loop)
    handler.get({'term': 'ubisoft'})
    parts[1].result = AppError('UPSTREAM_ERROR')
    with pytest.raises(CollectionFailed) as raised:
        handler.get({'term': 'ubisoft', 'freshness': 'live'})
    assert raised.value.code == 'UPSTREAM_ERROR'
    assert raised.value.retryable is True
    assert raised.value.last_good['collection']['term'] == 'ubisoft'


def test_a_failure_keeps_the_rate_limit_wait(parts, loop):
    parts[1].result = AppError('RATE_LIMITED', retry_after_seconds=30)
    with pytest.raises(CollectionFailed) as raised:
        posts_handler(parts, loop).get({'term': 'ubisoft'})
    assert raised.value.retry_after_seconds == 30
    assert raised.value.last_good is None


def test_a_hanging_collection_times_out(parts, loop):
    collector = parts[1]
    loop.call(collector.hold, 1)
    started = time.monotonic()
    try:
        with pytest.raises(AppError) as raised:
            posts_handler(parts, loop, timeout=0.1).get({'term': 'ubisoft'})
        assert raised.value.code == 'UPSTREAM_TIMEOUT'
        assert time.monotonic() - started < 1
    finally:
        loop.call(collector.release, 1)


def test_health_reports_mode_and_threshold(parts, loop):
    config = load_config({'COLLECTOR_MODE': 'fixture', 'STALE_AFTER_SECONDS': '900'})
    assert HealthHandler(parts[2], config, loop).get({}) == {
        'status': 'ok',
        'db': 'ok',
        'collectorMode': 'fixture',
        'staleAfterSeconds': 900,
    }


class BrokenRepository:
    def ping(self):
        raise AppError('DB_ERROR')


def test_health_reports_a_database_error(loop):
    reply = HealthHandler(BrokenRepository(), load_config({}), loop).get({})
    assert (reply['status'], reply['db']) == ('error', 'error')


def test_a_reddit_timeout_also_carries_the_last_good_feed(parts, loop):
    handler = posts_handler(parts, loop)
    handler.get({'term': 'ubisoft'})
    parts[1].result = AppError('UPSTREAM_TIMEOUT')
    with pytest.raises(CollectionFailed) as raised:
        handler.get({'term': 'ubisoft', 'freshness': 'live'})
    assert raised.value.last_good['collection']['term'] == 'ubisoft'


class FailsWhenReleased:
    """Fails with a new error once released, so no test keeps the error (or its task) alive."""

    def __init__(self):
        self.gate = None

    async def collect(self, subreddit, limit):
        self.gate = asyncio.Event()
        await self.gate.wait()
        raise AppError('UPSTREAM_ERROR')


def test_a_collection_that_fails_after_every_waiter_left_logs_no_asyncio_error(loop, caplog):
    clock = FakeClock()
    db, repository = loop.call(lambda: memory_repository(clock), 1)
    collector = FailsWhenReleased()
    service = CollectionService(
        repository=repository,
        collector=collector,
        normalizer=make_normalizer(),
        clock=clock,
        max_posts=25,
        ttl_seconds=60,
        logger=make_logger(),
    )
    with pytest.raises(AppError):
        PostsHandler(service, loop, 0.1).get({'term': 'ubisoft'})
    loop.call(lambda: collector.gate.set(), 1)
    loop.run(asyncio.sleep(0.05), 1)
    loop.call(gc.collect, 1)
    loop.run(asyncio.sleep(0.05), 1)
    loop.call(db.close, 1)

    assert 'never retrieved' not in caplog.text


class SlowLastGood:
    """Collection fails at once; the last good lookup blocks the loop for a while."""

    async def collect(self, term, force):
        raise AppError('RATE_LIMITED', retry_after_seconds=30)

    def last_good(self, term):
        time.sleep(0.5)


def test_a_slow_last_good_lookup_gives_up_quickly_and_keeps_the_original_error(loop):
    handler = PostsHandler(SlowLastGood(), loop, 10, lookup_timeout_seconds=0.1)
    started = time.monotonic()
    with pytest.raises(CollectionFailed) as raised:
        handler.get({'term': 'ubisoft'})
    assert time.monotonic() - started < 0.4
    assert (raised.value.code, raised.value.last_good) == ('RATE_LIMITED', None)
