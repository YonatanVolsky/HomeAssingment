import json
import socket
import threading
import time
from contextlib import contextmanager

from app.inner.server import ThreadPoolServer
from tests.helpers import make_logger


class Echo:
    def __init__(self, delay=0.0, error=None):
        self.lines = []
        self.delay = delay
        self.error = error

    def handle(self, line):
        self.lines.append(line)
        if self.delay:
            time.sleep(self.delay)
        if self.error is not None:
            raise self.error
        return b'ok:' + line


@contextmanager
def running(chain, threads=4, read_timeout_seconds=5.0):
    server = ThreadPoolServer('127.0.0.1', 0, threads, chain, make_logger(), read_timeout_seconds)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        thread.join(5)


def exchange(address, chunks, *, pause=0.0, half_close=False, timeout=5.0):
    with socket.create_connection(address, timeout=timeout) as client:
        for chunk in [chunks] if isinstance(chunks, bytes) else chunks:
            client.sendall(chunk)
            time.sleep(pause)
        if half_close:
            client.shutdown(socket.SHUT_WR)
        received = b''
        while data := client.recv(65536):
            received += data
        return received


def error_code(reply):
    return json.loads(reply)['error']['code']


def test_round_trip():
    with running(Echo()) as server:
        assert exchange(server.address, b'hello\n') == b'ok:hello\n'


def test_an_oversize_line_gets_invalid_request():
    chain = Echo()
    with running(chain) as server:
        reply = exchange(server.address, b'x' * 5000, half_close=True)
    assert error_code(reply) == 'INVALID_REQUEST'
    assert chain.lines == []


def test_a_silent_client_is_closed_without_a_reply():
    with running(Echo(), read_timeout_seconds=0.2) as server:
        started = time.monotonic()
        assert exchange(server.address, b'') == b''
        assert time.monotonic() - started < 1


def test_a_partial_line_then_close_gets_no_reply_and_frees_the_worker():
    chain = Echo()
    with running(chain, threads=1) as server:
        assert exchange(server.address, b'{"v":1', half_close=True) == b''
        assert exchange(server.address, b'next\n') == b'ok:next\n'
    assert chain.lines == [b'next\n']


def test_a_character_split_across_writes_is_reassembled():
    chain = Echo()
    raw = '{"t":"é"}\n'.encode()
    split = raw.index(b'\xc3') + 1
    with running(chain) as server:
        exchange(server.address, [raw[:split], raw[split:]], pause=0.05)
    assert chain.lines == [raw]


def test_more_connections_than_threads_are_all_answered():
    replies = []
    with running(Echo(delay=0.2), threads=2) as server:

        def ask(i):
            replies.append(exchange(server.address, b'%d\n' % i))

        clients = [threading.Thread(target=ask, args=(i,)) for i in range(6)]
        for client in clients:
            client.start()
        for client in clients:
            client.join(5)
    assert sorted(replies) == sorted(b'ok:%d\n' % i for i in range(6))


def test_shutdown_waits_for_a_running_request():
    server = ThreadPoolServer('127.0.0.1', 0, 2, Echo(delay=0.3), make_logger())
    serving = threading.Thread(target=server.serve_forever, daemon=True)
    serving.start()
    result = []
    client = threading.Thread(target=lambda: result.append(exchange(server.address, b'slow\n')))
    client.start()
    time.sleep(0.1)
    server.shutdown()
    client.join(5)
    serving.join(5)
    assert result == [b'ok:slow\n']


def test_a_chain_exception_is_an_internal_reply_not_a_crash():
    with running(Echo(error=RuntimeError('boom'))) as server:
        assert error_code(exchange(server.address, b'a\n')) == 'INTERNAL'
        assert error_code(exchange(server.address, b'b\n')) == 'INTERNAL'


def trickle(address, first, byte_every, seconds):
    """Sends `first`, then one byte every `byte_every` seconds, until the server hangs up."""
    with socket.create_connection(address, timeout=5) as client:
        client.sendall(first)
        deadline = time.monotonic() + seconds
        try:
            while time.monotonic() < deadline:
                time.sleep(byte_every)
                client.sendall(b'x')
        except OSError:
            pass  # the server closed the connection, as it should


def answered_within(address, request, seconds):
    started = time.monotonic()
    reply = exchange(address, request)
    return reply, time.monotonic() - started < seconds


def test_a_trickling_client_is_cut_off_after_the_whole_line_timeout():
    with running(Echo(), threads=1, read_timeout_seconds=0.5) as server:
        slow = threading.Thread(target=trickle, args=(server.address, b'{', 0.1, 3))
        slow.start()
        time.sleep(0.1)
        reply, quick = answered_within(server.address, b'next\n', 1.5)
        slow.join(5)
    assert reply == b'ok:next\n'
    assert quick


def test_a_client_trickling_after_an_oversize_line_does_not_hold_the_worker():
    with running(Echo(), threads=1) as server:
        slow = threading.Thread(target=trickle, args=(server.address, b'x' * 5000, 0.1, 3))
        slow.start()
        time.sleep(0.2)
        reply, quick = answered_within(server.address, b'next\n', 1.5)
        slow.join(5)
    assert reply == b'ok:next\n'
    assert quick


def test_shutdown_without_serving_returns_promptly():
    server = ThreadPoolServer('127.0.0.1', 0, 2, Echo(), make_logger())
    stopper = threading.Thread(target=server.shutdown, daemon=True)
    stopper.start()
    stopper.join(2)
    assert not stopper.is_alive()
