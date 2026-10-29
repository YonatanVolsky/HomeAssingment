import asyncio

from app.db.connection import open_database
from app.db.repository import Repository
from app.db.schema import ensure_schema
from tests.helpers import make_logger, make_post


class FakeCollector:
    """A collector whose result the test controls, and which counts its calls."""

    def __init__(self):
        self.calls = []
        self.result = [make_post('t3_a'), make_post('t3_b')]
        self._gate: asyncio.Event | None = None

    async def collect(self, subreddit, limit):
        self.calls.append((subreddit, limit))
        if self._gate is not None:
            await self._gate.wait()
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result

    def hold(self):
        self._gate = asyncio.Event()

    def release(self):
        assert self._gate is not None
        self._gate.set()


def memory_repository(clock):
    db = open_database(':memory:')
    ensure_schema(db)
    return db, Repository(db, clock, make_logger())
