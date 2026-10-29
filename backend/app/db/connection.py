import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

IN_MEMORY = ':memory:'


def open_database(path: str) -> sqlite3.Connection:
    if path != IN_MEMORY:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    # Autocommit mode: transactions are explicit (see `transaction`). One connection is shared
    # by the event loop thread, so the same-thread check is off.
    db = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA journal_mode = WAL')
    db.execute('PRAGMA foreign_keys = ON')
    db.execute('PRAGMA busy_timeout = 5000')
    db.execute('PRAGMA synchronous = NORMAL')
    return db


@contextmanager
def transaction(db: sqlite3.Connection) -> Iterator[None]:
    db.execute('BEGIN IMMEDIATE')
    try:
        yield
    except BaseException:
        db.execute('ROLLBACK')
        raise
    db.execute('COMMIT')
