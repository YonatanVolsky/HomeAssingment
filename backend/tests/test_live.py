"""Opt-in live check: actually calls Reddit once. Run with `pytest -m live` (or npm run test:live).

Skipped by default (see pyproject.toml addopts '-m not live'). Needs network; it fetches an
anonymous token and the newest posts of r/ubisoft and asserts the feed looks real.
"""

import pytest

from app.clock import SystemClock
from app.collector.factory import create_collector
from app.config import load_config
from tests.helpers import make_logger

pytestmark = [pytest.mark.anyio, pytest.mark.live]


async def test_collects_real_posts_from_reddit():
    collector = create_collector(load_config({}), clock=SystemClock(), logger=make_logger())

    posts = await collector.collect('ubisoft', 10)

    assert len(posts) >= 1, 'expected at least one post from r/ubisoft'
    first = posts[0]
    assert first.id.startswith('t3_')
    assert first.title
    assert first.permalink.startswith('https://www.reddit.com/r/ubisoft/')
    assert first.created_at.endswith('Z')
    # Newest-first ordering
    times = [p.created_at for p in posts]
    assert times == sorted(times, reverse=True)
    print(f'\\nLIVE OK: {len(posts)} posts; newest: {first.created_at} | {first.title[:60]}')
