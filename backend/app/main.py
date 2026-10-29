import logging
import os
import sys
from collections.abc import Callable, Mapping
from pathlib import Path

import uvicorn
from fastapi import FastAPI

from app.api import build_app
from app.clock import SystemClock
from app.collector.factory import create_collector
from app.collector.reddit.mobile_api import LIVE_COLLECTION_AVAILABLE
from app.config import ConfigError, load_config
from app.db.connection import open_database
from app.db.repository import Repository
from app.db.schema import ensure_schema

# Relative paths in the configuration mean "from the repository root", wherever you start.
REPO_ROOT = Path(__file__).resolve().parents[2]

logger = logging.getLogger('app')


def create_app_from_env(env: Mapping[str, str]) -> tuple[FastAPI, Callable[[], None]]:
    """Wires the real dependencies. Returns the app and a function that closes the database."""
    config = load_config(env)
    db_path = Path(config.db_path)
    if not db_path.is_absolute():
        db_path = REPO_ROOT / db_path
    db = open_database(str(db_path))
    ensure_schema(db)

    clock = SystemClock()
    app = build_app(
        repository=Repository(db, clock, logger),
        collector=create_collector(config, clock=clock, logger=logger),
        clock=clock,
        config=config,
        static_dir=REPO_ROOT / 'frontend' / 'dist',
    )
    logger.info('database: %s, collector mode: %s', db_path, config.collector_mode)
    if config.collector_mode == 'live' and not LIVE_COLLECTION_AVAILABLE:
        print(
            'WARNING: live Reddit collection is not available yet; searches will fail. '
            'Start with COLLECTOR_MODE=fixture for sample data.',
            file=sys.stderr,
        )
    return app, db.close


def run() -> None:
    try:
        config = load_config(os.environ)
    except ConfigError as error:
        print(error, file=sys.stderr)
        sys.exit(1)
    logging.basicConfig(
        level=config.log_level.upper(), format='%(levelname)s %(name)s: %(message)s'
    )
    app, close = create_app_from_env(os.environ)
    try:
        uvicorn.run(app, host=config.host, port=config.port, log_level=config.log_level)
    finally:
        close()
