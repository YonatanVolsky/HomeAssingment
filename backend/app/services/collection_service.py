import asyncio
import logging

from app.clock import Clock
from app.collector.types import Collector
from app.contracts import CollectionResponse, CollectionSource, CollectionSummary
from app.db.repository import Repository, StoredCollection
from app.errors import AppError


class CollectionService:
    """Orchestrates one collection.

    Takes a subreddit name the request stage has already normalized. Serves a fresh stored
    result if there is one, otherwise collects live (sharing a run already in progress for the
    same name) and stores the outcome. What the user sees is always read back from the database.
    """

    def __init__(
        self,
        *,
        repository: Repository,
        collector: Collector,
        clock: Clock,
        max_posts: int,
        ttl_seconds: int,
        logger: logging.Logger,
    ) -> None:
        self._repository = repository
        self._collector = collector
        self._clock = clock
        self._max_posts = max_posts
        self._ttl_seconds = ttl_seconds
        self._logger = logger
        self._in_flight: dict[str, asyncio.Task[CollectionResponse]] = {}

    async def collect(self, subreddit: str, force: bool) -> CollectionResponse:
        if not force:
            fresh = self._repository.get_fresh_success(subreddit, self._ttl_seconds)
            if fresh is not None:
                return self._to_response(fresh, 'cache')

        task = self._in_flight.get(subreddit)
        if task is None:
            task = asyncio.create_task(self._collect_live(subreddit))
            self._in_flight[subreddit] = task
            task.add_done_callback(lambda done: self._finished(subreddit, done))
        # Shielded: a request that goes away (client disconnect) must not cancel a run that
        # other requests are waiting on.
        return await asyncio.shield(task)

    def _finished(self, subreddit: str, task: asyncio.Task[CollectionResponse]) -> None:
        self._in_flight.pop(subreddit, None)
        # Every waiter may have timed out already. The failure is recorded in the database,
        # so mark it retrieved rather than have asyncio log it as unhandled.
        if not task.cancelled():
            task.exception()

    def last_good(self, subreddit: str) -> CollectionResponse | None:
        """The previous successful feed, or None. Best effort: never raises."""
        try:
            latest = self._repository.get_latest_success(subreddit)
        except AppError as error:
            self._logger.warning('could not load the last good feed', exc_info=error)
            return None
        return self._to_response(latest, 'cache') if latest else None

    def get_posts(self, subreddit: str) -> CollectionResponse:
        """Reads the stored feed only; never calls Reddit."""
        latest = self._repository.get_latest_success(subreddit)
        if latest is None:
            return CollectionResponse(collection=None, posts=[])
        return self._to_response(latest, 'cache')

    async def _collect_live(self, subreddit: str) -> CollectionResponse:
        started_at = self._clock.now()
        try:
            posts = await self._collector.collect(subreddit, self._max_posts)
            stored = self._repository.record_success(subreddit, posts, started_at)
        except AppError as error:
            self._repository.record_failure(subreddit, error.code, started_at)
            raise
        except Exception as raw:
            self._repository.record_failure(subreddit, 'INTERNAL', started_at)
            raise AppError('INTERNAL', cause=raw) from raw
        return self._to_response(stored, 'live')

    def _to_response(
        self, stored: StoredCollection, source: CollectionSource
    ) -> CollectionResponse:
        return CollectionResponse(
            collection=CollectionSummary(
                id=stored.id,
                term=stored.term,
                source=source,
                collected_at=stored.collected_at,
                post_count=stored.post_count,
            ),
            posts=self._repository.get_feed(stored.id),
        )
