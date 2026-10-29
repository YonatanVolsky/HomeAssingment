import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from app.clock import Clock
from app.errors import AppError


@dataclass(frozen=True)
class FetchedToken:
    access_token: str
    expires_in_seconds: int


TokenFetcher = Callable[[], Awaitable[FetchedToken]]
"""The app's anonymous token request. Reddit-specific; see docs/reddit-mobile-request.md."""

_REFRESH_MARGIN_SECONDS = 60
_PASS_THROUGH = {'UPSTREAM_TIMEOUT', 'RATE_LIMITED'}


class TokenProvider:
    """Caches the anonymous token until shortly before it expires.

    Concurrent callers share one refresh. The refresh is shielded and has its own timeout, so
    one collection hitting its deadline does not cancel the refresh others are waiting on.
    Failures are not cached, and the token value is never logged.
    """

    def __init__(
        self,
        fetch_token: TokenFetcher,
        clock: Clock,
        logger: logging.Logger,
        refresh_timeout_seconds: float = 10,
    ) -> None:
        self._fetch_token = fetch_token
        self._clock = clock
        self._logger = logger
        self._refresh_timeout = refresh_timeout_seconds
        self._cached: tuple[str, float] | None = None
        self._in_flight: asyncio.Task[str] | None = None

    async def get(self) -> str:
        now = self._clock.now().timestamp()
        if self._cached and now < self._cached[1] - _REFRESH_MARGIN_SECONDS:
            return self._cached[0]
        if self._in_flight is None:
            self._in_flight = asyncio.create_task(self._refresh())
            self._in_flight.add_done_callback(self._refresh_done)
        return await asyncio.shield(self._in_flight)

    def invalidate(self, rejected_token: str) -> None:
        """Drops the cached token only if it is the one that was rejected."""
        if self._cached and self._cached[0] == rejected_token:
            self._cached = None

    def _refresh_done(self, task: asyncio.Task[str]) -> None:
        self._in_flight = None
        if not task.cancelled():
            task.exception()  # Marks a failure as seen even if every waiter has gone.

    async def _refresh(self) -> str:
        try:
            async with asyncio.timeout(self._refresh_timeout):
                fetched = await self._fetch_token()
        except AppError as error:
            if error.code in _PASS_THROUGH:
                raise
            raise AppError('UPSTREAM_AUTH', cause=error) from error
        except TimeoutError as error:
            raise AppError('UPSTREAM_TIMEOUT', cause=error) from error
        except Exception as error:
            raise AppError('UPSTREAM_AUTH', cause=error) from error
        expires_at = self._clock.now().timestamp() + fetched.expires_in_seconds
        self._cached = (fetched.access_token, expires_at)
        self._logger.info('token refreshed, valid for %s s', fetched.expires_in_seconds)
        return fetched.access_token
