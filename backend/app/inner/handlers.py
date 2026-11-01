"""Resource handlers: one class per resource, one method per CRUD verb it supports."""

from collections.abc import Mapping
from typing import Any

from app.config import Config
from app.contracts import CollectionResponse
from app.db.repository import Repository
from app.errors import AppError
from app.inner.dispatcher import Command
from app.inner.loop_thread import LoopThread
from app.services.collection_service import CollectionService

# A fixed table, so a verb from the wire can never name an arbitrary method.
_VERB_METHODS = {'GET': 'get', 'POST': 'post', 'PUT': 'put', 'DELETE': 'delete'}
_NOT_SUPPORTED = 'This command is not supported for this resource.'


class ResourceHandler:
    """Calls the method for the command's verb. A resource overrides only what it supports."""

    def handle(self, command: Command) -> Any:
        method = _VERB_METHODS.get(command.verb)
        if method is None:
            raise AppError('INVALID_REQUEST', _NOT_SUPPORTED)
        return getattr(self, method)(command.args)

    def get(self, args: Mapping[str, Any]) -> Any:
        raise AppError('INVALID_REQUEST', _NOT_SUPPORTED)

    def post(self, args: Mapping[str, Any]) -> Any:
        raise AppError('INVALID_REQUEST', _NOT_SUPPORTED)

    def put(self, args: Mapping[str, Any]) -> Any:
        raise AppError('INVALID_REQUEST', _NOT_SUPPORTED)

    def delete(self, args: Mapping[str, Any]) -> Any:
        raise AppError('INVALID_REQUEST', _NOT_SUPPORTED)


class CollectionFailed(AppError):
    """A failed collection, with the last good feed for the same term (or None)."""

    def __init__(self, error: AppError, last_good: dict[str, Any] | None) -> None:
        super().__init__(
            error.code,
            error.message,
            cause=error,
            retry_after_seconds=error.retry_after_seconds,
            auto_retry=None if error.auto_retry else False,
            retryable=None if error.retryable else False,
        )
        self.last_good = last_good


_FRESHNESS = ('auto', 'live', 'stored')
# The last good feed is one database read; it must not hold a failed request much longer.
_LOOKUP_TIMEOUT_SECONDS = 5.0


class PostsHandler(ResourceHandler):
    """GET posts: the collection matching the term, stored or collected per `freshness`."""

    def __init__(
        self,
        service: CollectionService,
        loop: LoopThread,
        timeout_seconds: float,
        lookup_timeout_seconds: float = _LOOKUP_TIMEOUT_SECONDS,
    ) -> None:
        self._service = service
        self._loop = loop
        self._timeout = timeout_seconds
        self._lookup_timeout = lookup_timeout_seconds

    def get(self, args: Mapping[str, Any]) -> Any:
        term = args.get('term')
        freshness = args.get('freshness', 'auto')
        if not isinstance(term, str) or freshness not in _FRESHNESS:
            raise AppError('INVALID_REQUEST')
        if freshness == 'stored':
            return _dump(self._loop.call(lambda: self._service.get_posts(term), self._timeout))
        try:
            response = self._loop.run(
                self._service.collect(term, force=freshness == 'live'), self._timeout
            )
        except AppError as error:
            if error.code == 'INVALID_TERM':
                raise
            raise CollectionFailed(error, self._last_good(term)) from error
        return _dump(response)

    def _last_good(self, term: str) -> dict[str, Any] | None:
        """Best effort: a slow or failed lookup must not replace the collection's error."""
        try:
            last_good = self._loop.call(lambda: self._service.last_good(term), self._lookup_timeout)
        except AppError:
            return None
        return _dump(last_good) if last_good else None


class HealthHandler(ResourceHandler):
    """GET health: database reachability and the settings the UI needs."""

    def __init__(self, repository: Repository, config: Config, loop: LoopThread) -> None:
        self._repository = repository
        self._config = config
        self._loop = loop

    def get(self, args: Mapping[str, Any]) -> Any:
        try:
            self._loop.call(self._repository.ping, 5)
            status = 'ok'
        except AppError:
            status = 'error'
        return {
            'status': status,
            'db': status,
            'collectorMode': self._config.collector_mode,
            'staleAfterSeconds': self._config.stale_after_seconds,
        }


def _dump(response: CollectionResponse) -> dict[str, Any]:
    return response.model_dump(by_alias=True)
