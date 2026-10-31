"""One asyncio event loop on a background thread, for blocking worker threads to use.

The inner server's workers are plain threads; the collector, token cache and service are
async. Every such call is sent here, so the async code keeps its single-loop guarantees
(shared in-flight runs, one token refresh) and SQLite is only used from this one thread.
"""

import asyncio
import concurrent.futures
import threading
from collections.abc import Callable, Coroutine
from typing import Any, TypeVar

from app.errors import AppError

T = TypeVar('T')


class LoopThread:
    def __init__(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, name='loop', daemon=True)
        self._thread.start()

    @property
    def is_alive(self) -> bool:
        return self._thread.is_alive()

    def run(self, coro: Coroutine[Any, Any, T], timeout: float) -> T:
        """Runs `coro` on the loop and waits; raises UPSTREAM_TIMEOUT after `timeout` seconds."""
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        try:
            return future.result(timeout)
        except concurrent.futures.TimeoutError as error:
            future.cancel()
            raise AppError('UPSTREAM_TIMEOUT', cause=error) from error

    def call(self, fn: Callable[[], T], timeout: float) -> T:
        """Runs a plain function on the loop thread and waits for its result."""

        async def invoke() -> T:
            return fn()

        return self.run(invoke(), timeout)

    def stop(self) -> None:
        """Stops the loop and joins its thread. Safe to call more than once."""
        if self._loop.is_closed():
            return
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join()
        self._loop.close()
