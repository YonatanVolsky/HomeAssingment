import asyncio
import logging

from app.clock import Clock
from app.collector.normalize_term import normalize_term
from app.collector.types import Collector
from app.contracts import CollectionResponse, CollectionSource, CollectionSummary
from app.db.repository import Repository, StoredCollection
from app.errors import AppError


class CollectionService:
    """Orchestrates one collection.

    Validate the term, serve a fresh stored result if there is one, otherwise collect live
    (sharing a run already in progress for the same term) and store the outcome. What the user
    sees is always read back from the database.
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

    async def collect(self, term: str, force: bool) -> CollectionResponse:
        subreddit = normalize_term(term)
        if not force:
            fresh = self._repository.get_fresh_success(subreddit, self._ttl_seconds)
            if fresh is not None:
                return self._to_response(fresh, 'cache')

        task = self._in_flight.get(subreddit)
        if task is None:
            task = asyncio.create_task(self._collect_live(subreddit))
            self._in_flight[subreddit] = task
            task.add_done_callback(lambda _: self._in_flight.pop(subreddit, None))
        # Shielded: a request that goes away (client disconnect) must not cancel a run that
        # other requests are waiting on.
        return await asyncio.shield(task)

    def last_good(self, term: str) -> CollectionResponse | None:
        """The previous successful feed for a term, or None. Best effort: never raises."""
        try:
            latest = self._repository.get_latest_success(normalize_term(term))
        except AppError as error:
            if error.code != 'INVALID_TERM':
                self._logger.warning('could not load the last good feed', exc_info=error)
            return None
        return self._to_response(latest, 'cache') if latest else None

    def get_posts(self, term: str) -> CollectionResponse:
        """Reads the stored feed only; never calls Reddit."""
        latest = self._repository.get_latest_success(normalize_term(term))
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
