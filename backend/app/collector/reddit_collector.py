import asyncio
import random as random_module
from collections.abc import Awaitable, Callable
from typing import Protocol

from app.collector.classify import classify_network_error
from app.contracts import Post
from app.errors import AppError


class ListingSource(Protocol):
    """Sends the app's listing request and parses it. Reddit-specific; built from the capture."""

    async def fetch_new_posts(self, subreddit: str, limit: int, token: str) -> list[Post]: ...


class TokenSource(Protocol):
    async def get(self) -> str: ...

    def invalidate(self, rejected_token: str) -> None: ...


def deadline_error(cause: BaseException | None = None) -> AppError:
    return AppError('UPSTREAM_TIMEOUT', cause=cause, auto_retry=False)


class RedditCollector:
    """The reliability policy around Reddit, and nothing Reddit-specific.

    One deadline per collection, retries with backoff for transient failures (as the error
    table says), and one token refresh on an auth failure.
    """

    def __init__(
        self,
        *,
        tokens: TokenSource,
        source: ListingSource,
        deadline_seconds: float,
        max_retries: int = 2,
        base_delay_seconds: float = 0.25,
        random: Callable[[], float] = random_module.random,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._tokens = tokens
        self._source = source
        self._deadline_seconds = deadline_seconds
        self._max_retries = max_retries
        self._base_delay = base_delay_seconds
        self._random = random
        self._sleep = sleep

    async def collect(self, subreddit: str, limit: int) -> list[Post]:
        loop = asyncio.get_running_loop()
        deadline_at = loop.time() + self._deadline_seconds
        try:
            async with asyncio.timeout_at(deadline_at):
                return await self._with_retry(subreddit, limit, deadline_at)
        except TimeoutError as error:
            raise deadline_error(error) from error

    async def _with_retry(self, subreddit: str, limit: int, deadline_at: float) -> list[Post]:
        loop = asyncio.get_running_loop()
        attempt = self._attempt_with_auth_refresh(subreddit, limit)
        retry = 0
        while True:
            try:
                return await attempt()
            except Exception as raw:
                error = classify_network_error(raw)
            if not error.auto_retry or retry >= self._max_retries:
                raise error
            backoff = self._base_delay * 2**retry + self._random() * self._base_delay
            if backoff >= deadline_at - loop.time():
                raise error
            await self._sleep(backoff)
            retry += 1

    def _attempt_with_auth_refresh(
        self, subreddit: str, limit: int
    ) -> Callable[[], Awaitable[list[Post]]]:
        """One attempt; on the first auth failure of this collection, refresh and resend."""
        refreshed = False

        async def send() -> tuple[str | None, list[Post] | BaseException]:
            token: str | None = None
            try:
                token = await self._tokens.get()
                return token, await self._source.fetch_new_posts(subreddit, limit, token)
            except Exception as error:
                return token, error

        async def attempt() -> list[Post]:
            nonlocal refreshed
            token, result = await send()
            if not isinstance(result, BaseException):
                return result
            if refreshed or classify_network_error(result).code != 'UPSTREAM_AUTH':
                raise result
            refreshed = True
            if token is not None:
                self._tokens.invalidate(token)
            _, retried = await send()
            if isinstance(retried, BaseException):
                raise retried
            return retried

        return attempt
