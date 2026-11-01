"""Runs the inner collector server: python -m app.inner"""

import errno
import logging
import os
import signal
import sys
import threading

from app.composition import build_inner, configure_logging, resolve_db_path
from app.config import ConfigError, load_config

logger = logging.getLogger('app.inner')


def main() -> None:
    try:
        config = load_config(os.environ)
        configure_logging(config)
        app = build_inner(config, logger=logger)
    except ConfigError as error:
        print(error, file=sys.stderr)
        sys.exit(1)
    except OSError as error:
        reason = 'the port is already in use' if error.errno == errno.EADDRINUSE else error
        print(
            f'inner server could not listen on {config.inner_host}:{config.inner_port}: {reason}',
            file=sys.stderr,
        )
        sys.exit(1)

    def stop(_signum: int, _frame: object) -> None:
        # shutdown() waits for serve_forever to return, so it must run off the main thread.
        threading.Thread(target=app.server.shutdown, daemon=True).start()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    host, port = app.server.address
    logger.info(
        'inner server listening on %s:%s (database: %s, collector mode: %s)',
        host,
        port,
        resolve_db_path(config),
        config.collector_mode,
    )
    try:
        app.server.serve_forever()
    finally:
        app.close()


if __name__ == '__main__':
    main()
