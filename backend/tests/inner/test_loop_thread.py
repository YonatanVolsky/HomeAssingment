import asyncio
import threading
import time

import pytest

from app.errors import AppError
from app.inner.loop_thread import LoopThread


@pytest.fixture
def loop():
    loop = LoopThread()
    yield loop
    loop.stop()


def test_run_returns_the_coroutine_result(loop):
    assert loop.run(asyncio.sleep(0, 'x'), 1) == 'x'


def test_run_reraises_the_same_exception(loop):
    error = AppError('DB_ERROR')

    async def fail():
        raise error

    with pytest.raises(AppError) as raised:
        loop.run(fail(), 1)
    assert raised.value is error


def test_run_times_out_with_upstream_timeout(loop):
    started = time.monotonic()
    with pytest.raises(AppError) as raised:
        loop.run(asyncio.sleep(10), 0.05)
    assert raised.value.code == 'UPSTREAM_TIMEOUT'
    assert time.monotonic() - started < 1


def test_call_runs_on_the_loop_thread(loop):
    async def ident():
        return threading.get_ident()

    loop_ident = loop.run(ident(), 1)
    assert loop.call(threading.get_ident, 1) == loop_ident
    assert loop_ident != threading.get_ident()


def test_stop_is_idempotent_and_joins():
    loop = LoopThread()
    loop.stop()
    loop.stop()
    assert not loop.is_alive
