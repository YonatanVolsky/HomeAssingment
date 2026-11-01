"""One request to the inner server: one JSON line out, one JSON line back, per connection.

See docs/inner-protocol.md. The same rules as the web service's client
(server/src/innerClient.js): a deadline for the whole reply and a size cap.
"""

import json
import socket
import time
from typing import Any

MAX_REPLY_BYTES = 1024 * 1024


class ConnectionFailed(Exception):
    """No usable reply. The message is meant for the person at the prompt."""


class InnerConnection:
    def __init__(self, host: str, port: int, timeout_seconds: float) -> None:
        self.host = host
        self.port = port
        self._timeout = timeout_seconds

    def send(self, message: dict[str, Any]) -> dict[str, Any]:
        deadline = time.monotonic() + self._timeout
        line = (json.dumps(message, separators=(',', ':')) + '\n').encode()
        try:
            with socket.create_connection((self.host, self.port), self._timeout) as connection:
                connection.sendall(line)
                reply = self._read_line(connection, deadline)
        except TimeoutError as error:
            raise ConnectionFailed(f'no reply within {self._timeout:g} s') from error
        except OSError as error:
            raise ConnectionFailed(
                f'collector not reachable at {self.host}:{self.port} ({error.strerror or error})'
            ) from error
        return _parse(reply)

    def _read_line(self, connection: socket.socket, deadline: float) -> bytes:
        received = bytearray()
        while (end := received.find(b'\n')) == -1:
            if len(received) > MAX_REPLY_BYTES:
                raise ConnectionFailed('the reply is too large')
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError
            connection.settimeout(remaining)
            chunk = connection.recv(65536)
            if not chunk:
                raise ConnectionFailed('the collector closed the connection before replying')
            received += chunk
        return bytes(received[:end])


def _parse(line: bytes) -> dict[str, Any]:
    try:
        reply = json.loads(line.decode('utf-8'))
    except (UnicodeDecodeError, ValueError):
        reply = None
    if not _is_protocol_reply(reply):
        raise ConnectionFailed('the collector sent something that is not a protocol reply')
    return reply


def _is_protocol_reply(reply: Any) -> bool:
    if not isinstance(reply, dict):
        return False
    if reply.get('ok') is True:
        return 'result' in reply
    error = reply.get('error')
    return (
        reply.get('ok') is False
        and isinstance(error, dict)
        and isinstance(error.get('code'), str)
        and isinstance(error.get('message'), str)
        and isinstance(error.get('retryable'), bool)
    )
