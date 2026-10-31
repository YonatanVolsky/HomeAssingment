import logging

from app.clock import Clock
from app.collector.fixture_collector import DEFAULT_SAMPLE_FILE, FixtureCollector
from app.collector.reddit.mobile_api import (
    create_anonymous_token_fetcher,
    create_mobile_listing_source,
)
from app.collector.reddit_collector import RedditCollector
from app.collector.token_provider import TokenProvider
from app.collector.types import Collector
from app.config import Config
from app.terms.normalizer import TermNormalizer
from app.terms.presets import PRESETS


def create_collector(config: Config, *, clock: Clock, logger: logging.Logger) -> Collector:
    if config.collector_mode == 'fixture':
        return FixtureCollector.from_file(DEFAULT_SAMPLE_FILE, clock)
    return RedditCollector(
        tokens=TokenProvider(create_anonymous_token_fetcher(config), clock, logger),
        source=create_mobile_listing_source(config),
        deadline_seconds=config.collection_deadline_ms / 1000,
    )


def create_term_normalizer(config: Config) -> TermNormalizer:
    """The normalizer for the term protocol this deployment selected with TERM_PROTOCOL."""
    return TermNormalizer(PRESETS[config.term_protocol])
