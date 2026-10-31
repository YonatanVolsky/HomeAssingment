"""Builds the application's parts from configuration: the one place that picks presets."""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from app.clock import SystemClock
from app.collector.factory import create_collector
from app.collector.types import Collector
from app.config import Config, ConfigError
from app.db.connection import open_database
from app.db.repository import Repository
from app.db.schema import ensure_schema
from app.inner.dispatcher import CommandHandler, Dispatcher
from app.inner.handlers import HealthHandler, PostsHandler
from app.inner.loop_thread import LoopThread
from app.inner.normalizer import RequestNormalizer
from app.inner.presets import INNER_ROUTE_PRESETS, SERVER_PRESETS
from app.inner.server import InnerServer
from app.services.collection_service import CollectionService
from app.terms.normalizer import TermNormalizer
from app.terms.presets import PRESETS

# Relative paths in the configuration mean "from the repository root", wherever you start.
REPO_ROOT = Path(__file__).resolve().parents[2]

# How long a worker waits for one service call: the collection deadline plus a margin.
_TIMEOUT_MARGIN_SECONDS = 5


def configure_logging(config: Config) -> None:
    logging.basicConfig(
        level=config.log_level.upper(), format='%(levelname)s %(name)s: %(message)s'
    )


def resolve_db_path(config: Config) -> Path:
    path = Path(config.db_path)
    return path if path.is_absolute() else REPO_ROOT / path


def create_term_normalizer(config: Config) -> TermNormalizer:
    """The normalizer for the term protocol this deployment selected with TERM_PROTOCOL."""
    return TermNormalizer(PRESETS[config.term_protocol])


@dataclass
class InnerApp:
    server: InnerServer
    close: Callable[[], None]


def build_inner(
    config: Config, *, logger: logging.Logger, collector: Collector | None = None
) -> InnerApp:
    """Wires the inner server. `collector` replaces the configured one (tests)."""
    clock = SystemClock()
    db = open_database(str(resolve_db_path(config)))
    ensure_schema(db)
    repository = Repository(db, clock, logger)
    loop = LoopThread()
    try:
        service = CollectionService(
            repository=repository,
            collector=collector or create_collector(config, clock=clock, logger=logger),
            normalizer=create_term_normalizer(config),
            clock=clock,
            max_posts=config.max_posts,
            ttl_seconds=config.collection_ttl_seconds,
            logger=logger,
        )
        timeout = config.collection_deadline_ms / 1000 + _TIMEOUT_MARGIN_SECONDS
        handlers: dict[str, CommandHandler] = {
            'posts': PostsHandler(service, loop, timeout),
            'health': HealthHandler(repository, config, loop),
        }
        chain = RequestNormalizer(
            create_term_normalizer(config), _dispatcher(config, handlers), logger
        )
        server = SERVER_PRESETS[config.server](
            config.inner_host, config.inner_port, config.server_threads, chain, logger
        )
    except BaseException:
        loop.stop()
        db.close()
        raise

    closed = False

    def close() -> None:
        nonlocal closed
        if closed:
            return
        closed = True
        server.shutdown()
        loop.stop()
        db.close()

    return InnerApp(server, close)


def _dispatcher(config: Config, handlers: dict[str, CommandHandler]) -> Dispatcher:
    routes = INNER_ROUTE_PRESETS[config.inner_routes]
    missing = sorted(name for name in routes.values() if name not in handlers)
    if missing:
        raise ConfigError(
            f'INNER_ROUTES {config.inner_routes!r} names unknown handlers: {", ".join(missing)}'
        )
    return Dispatcher({resource: handlers[name] for resource, name in routes.items()})
