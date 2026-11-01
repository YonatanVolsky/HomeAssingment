"""Runs the interactive collector client: python -m app.client [--host H] [--port P]"""

import argparse
import contextlib
import os

from app.client.connection import InnerConnection
from app.client.repl import Repl

# Above the collector's own 30 s limit, like the web service's INNER_TIMEOUT_MS.
_DEFAULT_TIMEOUT_SECONDS = 35.0


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog='python -m app.client',
        description='Talk to the inner collector server directly over TCP.',
    )
    # argparse applies `type` to string defaults too, so a bad INNER_PORT is a usage error.
    parser.add_argument('--host', default=os.environ.get('INNER_HOST') or '127.0.0.1')
    parser.add_argument('--port', type=int, default=os.environ.get('INNER_PORT') or '3002')
    parser.add_argument(
        '--timeout', type=float, default=_DEFAULT_TIMEOUT_SECONDS, help='seconds per request'
    )
    args = parser.parse_args(argv)
    with contextlib.suppress(ImportError):  # line editing and history, where available
        import readline  # noqa: F401
    Repl(InnerConnection(args.host, args.port, args.timeout), input, print).run()


if __name__ == '__main__':
    main()
