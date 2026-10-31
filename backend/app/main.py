import logging
import os
import sys
from collections.abc import Callable, Mapping

import uvicorn
from fastapi import FastAPI

from app.api import build_app
from app.clock import SystemClock
from app.collector.factory import create_collector
from app.collector.reddit.mobile_api import LIVE_COLLECTION_AVAILABLE
from app.composition import (
    REPO_ROOT,
    configure_logging,
    create_term_normalizer,
    resolve_db_path,
)
from app.config import ConfigError, load_config
from app.db.connection import open_database
from app.db.repository import Repository
from app.db.schema import ensure_schema

logger = logging.getLogger('app')


def create_app_from_env(env: Mapping[str, str]) -> tuple[FastAPI, Callable[[], None]]:
    """Wires the real dependencies. Returns the app and a function that closes the database."""
    config = load_config(env)
    db_path = resolve_db_path(config)
    db = open_database(str(db_path))
    ensure_schema(db)

    clock = SystemClock()
    app = build_app(
        repository=Repository(db, clock, logger),
        collector=create_collector(config, clock=clock, logger=logger),
        normalizer=create_term_normalizer(config),
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
    configure_logging(config)
    app, close = create_app_from_env(os.environ)
    try:
        uvicorn.run(app, host=config.host, port=config.port, log_level=config.log_level)
    finally:
        close()
