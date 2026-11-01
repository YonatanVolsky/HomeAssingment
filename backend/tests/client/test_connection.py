import socket
import threading
import time

import pytest

from app.client.connection import ConnectionFailed, InnerConnection

MESSAGE = {'v': 1, 'command': 'GET', 'resource': 'health'}


@pytest.fixture
def fake_server():
    """Starts a one-connection-at-a-time TCP server running `respond(connection, line)`."""
    servers = []

    def start(respond):
        listener = socket.create_server(('127.0.0.1', 0))
        servers.append(listener)

        def serve():
            while True:
                try:
                    connection, _ = listener.accept()
                except OSError:
                    return
                with connection:
                    line = b''
                    while not line.endswith(b'\n') and (chunk := connection.recv(4096)):
                        line += chunk
                    respond(connection, line)

        threading.Thread(target=serve, daemon=True).start()
        return listener.getsockname()[1]

    yield start
    for listener in servers:
        listener.close()


def closed_port():
    with socket.create_server(('127.0.0.1', 0)) as listener:
        return listener.getsockname()[1]


def connect(port, timeout=2.0):
    return InnerConnection('127.0.0.1', port, timeout)


def test_sends_one_line_and_returns_the_reply(fake_server):
    received = []

    def respond(connection, line):
        received.append(line)
        connection.sendall(b'{"ok":true,"result":{"a":1}}\n')

    assert connect(fake_server(respond)).send(MESSAGE) == {'ok': True, 'result': {'a': 1}}
    assert received == [b'{"v":1,"command":"GET","resource":"health"}\n']


def test_a_reply_split_across_packets_is_reassembled(fake_server):
    def respond(connection, _line):
        for part in (b'{"ok":tr', b'ue,"result":', b'{"a":2}}\nignored'):
            connection.sendall(part)
            time.sleep(0.02)

    assert connect(fake_server(respond)).send(MESSAGE) == {'ok': True, 'result': {'a': 2}}


def test_nothing_listening_is_a_clear_failure():
    port = closed_port()
    with pytest.raises(ConnectionFailed) as raised:
        connect(port).send(MESSAGE)
    assert f'not reachable at 127.0.0.1:{port}' in str(raised.value)


def test_no_reply_in_time_is_a_timeout(fake_server):
    port = fake_server(lambda _connection, _line: time.sleep(1))
    started = time.monotonic()
    with pytest.raises(ConnectionFailed) as raised:
        connect(port, timeout=0.2).send(MESSAGE)
    assert 'no reply within 0.2 s' in str(raised.value)
    assert time.monotonic() - started < 0.9


def test_closing_without_a_full_reply_is_a_failure(fake_server):
    port = fake_server(lambda connection, _line: connection.sendall(b'{"ok":true'))
    with pytest.raises(ConnectionFailed, match='closed the connection'):
        connect(port).send(MESSAGE)


@pytest.mark.parametrize(
    'reply',
    [
        b'not json\n',
        b'[]\n',
        b'{"ok":true}\n',
        b'{"ok":false,"error":{}}\n',
        b'{"ok":false,"error":{"code":"X","message":"m","retryable":"yes"}}\n',
    ],
)
def test_a_reply_outside_the_protocol_is_a_failure(fake_server, reply):
    port = fake_server(lambda connection, _line: connection.sendall(reply))
    with pytest.raises(ConnectionFailed, match='not a protocol reply'):
        connect(port).send(MESSAGE)


def test_an_oversize_reply_is_a_failure(fake_server):
    port = fake_server(lambda connection, _line: connection.sendall(b'x' * (1024 * 1024 + 10)))
    with pytest.raises(ConnectionFailed, match='too large'):
        connect(port).send(MESSAGE)
