import sqlite3

import pytest

from app.db.connection import open_database
from app.db.repository import Repository
from app.db.schema import SCHEMA_VERSION, ensure_schema
from app.errors import AppError
from tests.helpers import FakeClock, make_logger, make_post


@pytest.fixture
def db():
    connection = open_database(':memory:')
    ensure_schema(connection)
    yield connection
    connection.close()


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def repo(db, clock):
    return Repository(db, clock, make_logger())


def count(db, table):
    return db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]


# Connection and schema


def test_open_database_creates_parent_directories(tmp_path):
    path = tmp_path / 'nested' / 'dir' / 'test.db'
    open_database(str(path)).close()
    assert path.exists()


def test_open_database_sets_pragmas_on_a_file(tmp_path):
    connection = open_database(str(tmp_path / 'test.db'))
    try:
        assert connection.execute('PRAGMA journal_mode').fetchone()[0] == 'wal'
        assert connection.execute('PRAGMA foreign_keys').fetchone()[0] == 1
        assert connection.execute('PRAGMA busy_timeout').fetchone()[0] == 5000
        assert connection.execute('PRAGMA synchronous').fetchone()[0] == 1
    finally:
        connection.close()


def test_schema_creates_three_tables_and_sets_user_version(db):
    tables = [
        row[0]
        for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    ]
    assert tables == ['collection_posts', 'collections', 'posts']
    assert db.execute('PRAGMA user_version').fetchone()[0] == SCHEMA_VERSION


def test_schema_is_idempotent_and_keeps_rows(db):
    db.execute(
        'INSERT INTO collections (term, status, post_count, started_at, finished_at) '
        "VALUES ('ubisoft', 'success', 0, 'a', 'b')"
    )
    ensure_schema(db)
    assert count(db, 'collections') == 1


def test_schema_rejects_duplicate_reddit_ids_and_unknown_statuses(db):
    insert = (
        'INSERT INTO posts (reddit_id, title, created_at, permalink, first_seen_at, last_seen_at) '
        "VALUES ('t3_a', 'x', 'c', 'p', 'f', 'l')"
    )
    db.execute(insert)
    with pytest.raises(sqlite3.IntegrityError, match='UNIQUE'):
        db.execute(insert)
    with pytest.raises(sqlite3.IntegrityError, match='CHECK'):
        db.execute(
            'INSERT INTO collections (term, status, started_at, finished_at) '
            "VALUES ('x', 'pending', 'a', 'b')"
        )


# record_success


def test_record_success_stores_posts_and_stamps_the_finish_time(repo, clock):
    started = clock.now()
    clock.advance(2)

    stored = repo.record_success('ubisoft', [make_post('t3_a'), make_post('t3_b')], started)

    assert (stored.term, stored.post_count) == ('ubisoft', 2)
    assert stored.collected_at == '2026-10-29T12:00:02.000Z'
    assert sorted(p.id for p in repo.get_feed(stored.id)) == ['t3_a', 't3_b']


def test_record_success_never_duplicates_posts_and_refreshes_counts(repo, db, clock):
    repo.record_success('ubisoft', [make_post('t3_a', comment_count=1)], clock.now())
    clock.advance(60)
    second = repo.record_success(
        'ubisoft', [make_post('t3_a', comment_count=9, title='Edited')], clock.now()
    )

    assert count(db, 'posts') == 1
    assert count(db, 'collections') == 2
    post = repo.get_feed(second.id)[0]
    assert (post.comment_count, post.title) == (9, 'Edited')


def test_record_success_keeps_first_seen_and_moves_last_seen(repo, db, clock):
    repo.record_success('ubisoft', [make_post('t3_a')], clock.now())
    clock.advance(60)
    repo.record_success('ubisoft', [make_post('t3_a')], clock.now())

    assert tuple(db.execute('SELECT first_seen_at, last_seen_at FROM posts').fetchone()) == (
        '2026-10-29T12:00:00.000Z',
        '2026-10-29T12:01:00.000Z',
    )


def test_a_post_under_two_terms_is_one_row_linked_from_both_runs(repo, db, clock):
    a = repo.record_success('ubisoft', [make_post('t3_shared')], clock.now())
    b = repo.record_success('gaming', [make_post('t3_shared')], clock.now())

    assert count(db, 'posts') == 1
    assert len(repo.get_feed(a.id)) == len(repo.get_feed(b.id)) == 1


def test_an_empty_run_is_a_success_with_zero_posts(repo, clock):
    stored = repo.record_success('quiet', [], clock.now())
    assert stored.post_count == 0
    assert repo.get_feed(stored.id) == []


def test_record_success_writes_nothing_when_one_post_fails(repo, db, clock):
    with pytest.raises(AppError):
        repo.record_success(
            'ubisoft', [make_post('t3_ok'), make_post('t3_bad', comment_count=-1)], clock.now()
        )
    assert count(db, 'posts') == count(db, 'collections') == count(db, 'collection_posts') == 0


def test_record_success_ignores_a_repeated_post_id(repo, clock):
    stored = repo.record_success('ubisoft', [make_post('t3_a'), make_post('t3_a')], clock.now())
    assert len(repo.get_feed(stored.id)) == 1


def test_feed_is_newest_first_with_reddit_id_as_tie_breaker(repo, clock):
    stored = repo.record_success(
        'ubisoft',
        [
            make_post('t3_b', created_at='2026-10-29T09:00:00.000Z'),
            make_post('t3_c', created_at='2026-10-29T11:00:00.000Z'),
            make_post('t3_a', created_at='2026-10-29T09:00:00.000Z'),
        ],
        clock.now(),
    )
    assert [p.id for p in repo.get_feed(stored.id)] == ['t3_c', 't3_a', 't3_b']


# record_failure and queries


def test_record_failure_keeps_the_latest_successful_feed(repo, db, clock):
    good = repo.record_success('ubisoft', [make_post('t3_a')], clock.now())
    clock.advance(30)

    repo.record_failure('ubisoft', 'UPSTREAM_TIMEOUT', clock.now())

    row = db.execute(
        "SELECT status, error_code, post_count FROM collections WHERE status = 'failed'"
    ).fetchone()
    assert tuple(row) == ('failed', 'UPSTREAM_TIMEOUT', 0)
    assert repo.get_latest_success('ubisoft').id == good.id


def test_record_failure_never_raises_and_logs_instead(db, clock, caplog):
    repo = Repository(db, clock, make_logger())
    db.close()

    repo.record_failure('ubisoft', 'UPSTREAM_ERROR', clock.now())

    assert any(record.levelname == 'ERROR' for record in caplog.records)


def test_latest_success_is_none_for_a_term_never_collected(repo):
    assert repo.get_latest_success('never') is None


def test_latest_success_is_the_newest_run_of_that_term(repo, clock):
    repo.record_success('ubisoft', [make_post('t3_a')], clock.now())
    clock.advance(10)
    newer = repo.record_success('ubisoft', [make_post('t3_b')], clock.now())
    repo.record_success('gaming', [make_post('t3_c')], clock.now())

    assert repo.get_latest_success('ubisoft').id == newer.id
    assert [p.id for p in repo.get_feed(newer.id)] == ['t3_b']


def test_fresh_success_respects_the_ttl(repo, clock):
    run = repo.record_success('ubisoft', [make_post('t3_a')], clock.now())
    clock.advance(59)
    assert repo.get_fresh_success('ubisoft', 60).id == run.id
    clock.advance(2)
    assert repo.get_fresh_success('ubisoft', 60) is None


def test_fresh_success_is_none_when_the_ttl_is_zero(repo, clock):
    repo.record_success('ubisoft', [make_post('t3_a')], clock.now())
    assert repo.get_fresh_success('ubisoft', 0) is None


def test_ping_succeeds_on_an_open_database(repo):
    repo.ping()


@pytest.mark.parametrize(
    'call',
    [
        lambda r: r.get_feed(1),
        lambda r: r.get_latest_success('x'),
        lambda r: r.get_fresh_success('x', 60),
        lambda r: r.record_success('x', [], FakeClock().now()),
        lambda r: r.ping(),
    ],
)
def test_database_failures_become_db_error_with_the_cause_kept(repo, db, call):
    db.close()
    with pytest.raises(AppError) as raised:
        call(repo)
    assert raised.value.code == 'DB_ERROR'
    assert raised.value.message == 'Could not save results locally.'
    assert isinstance(raised.value.__cause__, sqlite3.Error)
