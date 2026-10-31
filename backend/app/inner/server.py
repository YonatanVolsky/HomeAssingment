"""The inner server: one request line per TCP connection, served from a fixed thread pool.

The server only frames bytes: it reads one line (within the size and time limits), hands it
to the chain, writes the chain's reply line and closes. What the line means is the chain's job.
"""

import logging
import socketserver
from concurrent.futures import ThreadPoolExecutor
from typing import Protocol

from app.errors import AppError
from app.inner.protocol import MAX_LINE_BYTES, encode_error

_DRAIN_LIMIT_BYTES = 65536
_DRAIN_TIMEOUT_SECONDS = 0.5


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
    ) -> None:
        self._executor = ThreadPoolExecutor(max_workers=threads, thread_name_prefix='inner')
        self._tcp = _PooledTCPServer((host, port), self._executor)
        self._tcp.chain = chain
        self._tcp.logger = logger
        self._tcp.read_timeout_seconds = read_timeout_seconds

    @property
    def address(self) -> tuple[str, int]:
        host, port = self._tcp.server_address[:2]
        return str(host), int(port)

    def serve_forever(self) -> None:
        self._tcp.serve_forever(poll_interval=0.2)

    def shutdown(self) -> None:
        """Stops accepting, lets running and queued requests finish, then closes the socket."""
        self._tcp.shutdown()
        self._executor.shutdown(wait=True)
        self._tcp.server_close()


class _PooledTCPServer(socketserver.TCPServer):
    allow_reuse_address = True
    request_queue_size = 64
    chain: LineHandler
    logger: logging.Logger
    read_timeout_seconds: float

    def __init__(self, address: tuple[str, int], executor: ThreadPoolExecutor) -> None:
        self._executor = executor
        super().__init__(address, _LineRequestHandler)

    def process_request(self, request, client_address) -> None:  # type: ignore[no-untyped-def]
        self._executor.submit(self._process_in_worker, request, client_address)

    def _process_in_worker(self, request, client_address) -> None:  # type: ignore[no-untyped-def]
        try:
            self.finish_request(request, client_address)
        except Exception as error:
            self.logger.debug('connection %s ended with an error', client_address, exc_info=error)
        finally:
            self.shutdown_request(request)


class _LineRequestHandler(socketserver.StreamRequestHandler):
    server: _PooledTCPServer

    def setup(self) -> None:
        self.timeout = self.server.read_timeout_seconds
        super().setup()

    def handle(self) -> None:
        try:
            line = self.rfile.readline(MAX_LINE_BYTES + 1)
        except OSError:  # includes the read timeout
            self.server.logger.debug('no request line from %s', self.client_address)
            return
        if not line.endswith(b'\n'):
            if len(line) > MAX_LINE_BYTES:
                self._reply(encode_error(AppError('INVALID_REQUEST')))
                self._drain()
            return  # end of input before a full line: nothing to answer
        self._reply(self._run_chain(line))

    def _run_chain(self, line: bytes) -> bytes:
        try:
            return self.server.chain.handle(line)
        except Exception as error:
            self.server.logger.error('the request chain raised', exc_info=error)
            return encode_error(AppError('INTERNAL', cause=error))

    def _reply(self, data: bytes) -> None:
        try:
            self.wfile.write(data)
        except OSError:
            self.server.logger.debug('client %s left before the reply', self.client_address)

    def _drain(self) -> None:
        """Reads what the client is still sending, so closing does not reset the reply."""
        self.request.settimeout(_DRAIN_TIMEOUT_SECONDS)
        received = 0
        try:
            while received < _DRAIN_LIMIT_BYTES and (data := self.request.recv(4096)):
                received += len(data)
        except OSError:  # includes the drain timeout
            pass
