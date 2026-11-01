"""The inner server: one request line per TCP connection, served from a fixed thread pool.

The server only frames bytes: it reads one line (within the size and time limits), hands it
to the chain, writes the chain's reply line and closes. What the line means is the chain's job.
"""

import logging
import socket
import socketserver
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Protocol

from app.errors import AppError
from app.inner.protocol import MAX_LINE_BYTES, encode_error

_DRAIN_LIMIT_BYTES = 65536
_DRAIN_TIMEOUT_SECONDS = 0.5
_REFUSE_TIMEOUT_SECONDS = 0.5


class LineHandler(Protocol):
    def handle(self, line: bytes) -> bytes: ...


class InnerServer(Protocol):
    @property
    def address(self) -> tuple[str, int]: ...

    def serve_forever(self) -> None: ...

    def shutdown(self) -> None: ...


class ThreadPoolServer:
    def __init__(
        self,
        host: str,
        port: int,
        threads: int,
        chain: LineHandler,
        logger: logging.Logger,
        read_timeout_seconds: float = 5.0,
        queue_limit: int = 64,
    ) -> None:
        """`queue_limit`: connections that may wait for a free thread; beyond that, BUSY."""
        self._executor = ThreadPoolExecutor(max_workers=threads, thread_name_prefix='inner')
        self._tcp = _PooledTCPServer((host, port), self._executor, threads + queue_limit)
        self._tcp.chain = chain
        self._tcp.logger = logger
        self._tcp.read_timeout_seconds = read_timeout_seconds
        self._state = threading.Lock()
        self._serving = False
        self._stopped = False

    @property
    def address(self) -> tuple[str, int]:
        host, port = self._tcp.server_address[:2]
        return str(host), int(port)

    @property
    def pending(self) -> int:
        """Connections accepted and not yet finished: running plus queued."""
        return self._tcp.pending

    def serve_forever(self) -> None:
        with self._state:
            if self._stopped:
                return
            self._serving = True
        self._tcp.serve_forever(poll_interval=0.2)

    def shutdown(self) -> None:
        """Stops accepting, lets running and queued requests finish, then closes the socket.

        Safe before serve_forever has started: socketserver's own shutdown would wait forever.
        """
        with self._state:
            if self._stopped:
                return
            self._stopped = True
            serving = self._serving
        if serving:
            self._tcp.shutdown()
        self._executor.shutdown(wait=True)
        self._tcp.server_close()


class _PooledTCPServer(socketserver.TCPServer):
    allow_reuse_address = True
    request_queue_size = 64
    chain: LineHandler
    logger: logging.Logger
    read_timeout_seconds: float

    def __init__(
        self, address: tuple[str, int], executor: ThreadPoolExecutor, max_pending: int
    ) -> None:
        self._executor = executor
        self._max_pending = max_pending
        self._pending = 0
        self._pending_lock = threading.Lock()
        super().__init__(address, _LineRequestHandler)

    @property
    def pending(self) -> int:
        with self._pending_lock:
            return self._pending

    def process_request(self, request, client_address) -> None:  # type: ignore[no-untyped-def]
        with self._pending_lock:
            full = self._pending >= self._max_pending
            if not full:
                self._pending += 1
        if full:
            self._refuse(request)
            return
        self._executor.submit(self._process_in_worker, request, client_address)

    def _process_in_worker(self, request, client_address) -> None:  # type: ignore[no-untyped-def]
        try:
            self.finish_request(request, client_address)
        except Exception as error:
            self.logger.debug('connection %s ended with an error', client_address, exc_info=error)
        finally:
            self.shutdown_request(request)
            with self._pending_lock:
                self._pending -= 1

    def _refuse(self, request: socket.socket) -> None:
        """Answers BUSY on the accepting thread, so every step is bounded in time. After the
        reply, it reads until the client hangs up, so closing does not reset away the reply."""
        deadline = time.monotonic() + _REFUSE_TIMEOUT_SECONDS
        try:
            request.settimeout(_REFUSE_TIMEOUT_SECONDS)
            request.sendall(encode_error(AppError('BUSY')))
            request.shutdown(socket.SHUT_WR)
            drained = 0
            while drained < _DRAIN_LIMIT_BYTES and (remaining := deadline - time.monotonic()) > 0:
                request.settimeout(remaining)
                chunk = request.recv(4096)
                if not chunk:
                    break
                drained += len(chunk)
        except OSError:
            pass
        finally:
            self.shutdown_request(request)


class _LineTooLong(Exception):
    pass


class _LineRequestHandler(socketserver.BaseRequestHandler):
    """Reads one line with a deadline for the whole line, not per read, so a client sending
    a byte at a time cannot hold a worker longer than the read timeout."""

    server: _PooledTCPServer
    request: socket.socket

    def handle(self) -> None:
        try:
            line = self._read_line(time.monotonic() + self.server.read_timeout_seconds)
        except _LineTooLong:
            self._reply(encode_error(AppError('INVALID_REQUEST')))
            self._drain(time.monotonic() + _DRAIN_TIMEOUT_SECONDS)
            return
        if line is None:
            self.server.logger.debug('no complete request line from %s', self.client_address)
            return
        self._reply(self._run_chain(line))

    def _read_line(self, deadline: float) -> bytes | None:
        """The first line including its newline; None on end of input or the deadline."""
        received = bytearray()
        while True:
            chunk = self._recv_until(deadline, MAX_LINE_BYTES + 1 - len(received))
            if not chunk:
                return None
            received += chunk
            end = received.find(b'\n')
            if end != -1 and end < MAX_LINE_BYTES + 1:
                return bytes(received[: end + 1])
            if len(received) > MAX_LINE_BYTES:
                raise _LineTooLong

    def _recv_until(self, deadline: float, limit: int) -> bytes:
        remaining = deadline - time.monotonic()
        if remaining <= 0 or limit <= 0:
            return b''
        self.request.settimeout(remaining)
        try:
            return self.request.recv(min(limit, 4096))
        except OSError:  # includes the timeout
            return b''

    def _run_chain(self, line: bytes) -> bytes:
        try:
            return self.server.chain.handle(line)
        except Exception as error:
            self.server.logger.error('the request chain raised', exc_info=error)
            return encode_error(AppError('INTERNAL', cause=error))

    def _reply(self, data: bytes) -> None:
        try:
            self.request.settimeout(self.server.read_timeout_seconds)
            self.request.sendall(data)
        except OSError:
            self.server.logger.debug('client %s left before the reply', self.client_address)

    def _drain(self, deadline: float) -> None:
        """Reads what the client is still sending (bounded in bytes and time), so closing does
        not reset the connection and destroy the reply."""
        drained = 0
        while drained < _DRAIN_LIMIT_BYTES and (chunk := self._recv_until(deadline, 4096)):
            drained += len(chunk)
