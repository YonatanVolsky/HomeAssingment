import asyncio
import logging

import pytest

from app.collector.factory import create_collector
from app.collector.fixture_collector import (
    DEFAULT_SAMPLE_FILE,
    FixtureCollector,
    SamplePost,
)
from app.collector.reddit_collector import RedditCollector
from app.collector.token_provider import FetchedToken, TokenProvider
from app.config import load_config
from app.errors import ERROR_TABLE, AppError
from tests.helpers import FakeClock, make_logger, make_post

pytestmark = pytest.mark.anyio


# TokenProvider


def counting_fetcher(expires_in=3600):
    calls = {'n': 0}

    async def fetch():
        calls['n'] += 1
        return FetchedToken(f'token-{calls["n"]}', expires_in)

    return fetch, calls


def provider(fetch, clock=None):
    return TokenProvider(fetch, clock or FakeClock(), make_logger())


async def test_token_is_reused_while_valid():
    fetch, calls = counting_fetcher()
    tokens = provider(fetch)
    assert await tokens.get() == await tokens.get() == 'token-1'
    assert calls['n'] == 1


async def test_token_is_refreshed_60_seconds_before_expiry():
    fetch, _ = counting_fetcher(3600)
    clock = FakeClock()
    tokens = provider(fetch, clock)
    await tokens.get()
    clock.advance(3539)
    assert await tokens.get() == 'token-1'
    clock.advance(1)
    assert await tokens.get() == 'token-2'


async def test_concurrent_callers_share_one_refresh():
    fetch, calls = counting_fetcher()
    tokens = provider(fetch)
    assert await asyncio.gather(tokens.get(), tokens.get(), tokens.get()) == ['token-1'] * 3
    assert calls['n'] == 1


async def test_invalidating_the_rejected_token_fetches_a_new_one():
    fetch, _ = counting_fetcher()
    tokens = provider(fetch)
    tokens.invalidate(await tokens.get())
    assert await tokens.get() == 'token-2'


async def test_invalidating_a_stale_token_keeps_the_newer_one():
    fetch, _ = counting_fetcher()
    tokens = provider(fetch)
    stale = await tokens.get()
    tokens.invalidate(stale)
    await tokens.get()

    tokens.invalidate(stale)

    assert await tokens.get() == 'token-2'


async def test_a_failed_fetch_is_upstream_auth_and_not_cached():
    fail = {'now': True}

    async def fetch():
        if fail['now']:
            raise RuntimeError('HTTP 500 from token endpoint')
        return FetchedToken('recovered', 3600)

    tokens = provider(fetch)
    with pytest.raises(AppError) as raised:
        await tokens.get()
    assert raised.value.code == 'UPSTREAM_AUTH'
    fail['now'] = False
    assert await tokens.get() == 'recovered'


@pytest.mark.parametrize('code', ['UPSTREAM_TIMEOUT', 'RATE_LIMITED'])
async def test_timeouts_and_rate_limits_pass_through(code):
    async def fetch():
        raise AppError(code)

    with pytest.raises(AppError) as raised:
        await provider(fetch).get()
    assert raised.value.code == code


async def test_the_token_value_is_never_logged(caplog):
    caplog.set_level(logging.INFO)
    fetch, _ = counting_fetcher()
    await provider(fetch).get()
    assert 'token-1' not in caplog.text
    assert 'token refreshed' in caplog.text


async def test_one_caller_hitting_its_deadline_does_not_fail_the_others():
    release = asyncio.Event()

    async def fetch():
        await release.wait()
        return FetchedToken('shared', 3600)

    tokens = provider(fetch)
    first = asyncio.create_task(tokens.get())
    second = asyncio.create_task(tokens.get())
    await asyncio.sleep(0)
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first

    release.set()
    assert await second == 'shared'


# RedditCollector


class ScriptedSource:
    """Plays back one result per call: a list of posts, an exception, or 'hang'."""

    def __init__(self, *steps):
        self.steps = list(steps)
        self.tokens_seen = []

    async def fetch_new_posts(self, subreddit, limit, token):
        self.tokens_seen.append(token)
        step = self.steps.pop(0) if self.steps else RuntimeError('script exhausted')
        if step == 'hang':
            await asyncio.Event().wait()
        if isinstance(step, BaseException):
            raise step
        return step


class FakeTokens:
    def __init__(self):
        self.version = 1
        self.rejected = []

    async def get(self):
        return f'token-{self.version}'

    def invalidate(self, rejected_token):
        self.rejected.append(rejected_token)
        self.version += 1


def build(source, deadline_seconds=5.0, tokens=None):
    sleeps = []

    async def sleep(seconds):
        sleeps.append(seconds)

    collector = RedditCollector(
        tokens=tokens or FakeTokens(),
        source=source,
        deadline_seconds=deadline_seconds,
        random=lambda: 0,
        sleep=sleep,
    )
    return collector, sleeps


def network_error():
    import httpx

    return httpx.ConnectError('reset')


def timeout_error():
    import httpx

    return httpx.ReadTimeout('slow')


async def expect_code(coro, code):
    with pytest.raises(AppError) as raised:
        await coro
    assert raised.value.code == code
    return raised.value


async def test_collector_returns_posts_from_the_first_successful_attempt():
    source = ScriptedSource([make_post('t3_a')])
    collector, _ = build(source)
    assert len(await collector.collect('ubisoft', 25)) == 1
    assert len(source.tokens_seen) == 1


async def test_network_errors_are_retried_twice_with_exponential_backoff():
    source = ScriptedSource(network_error(), network_error(), [make_post('t3_a')])
    collector, sleeps = build(source)
    assert len(await collector.collect('ubisoft', 25)) == 1
    assert sleeps == [0.25, 0.5]


async def test_exhausted_timeouts_report_upstream_timeout():
    source = ScriptedSource(timeout_error(), timeout_error(), timeout_error())
    await expect_code(build(source)[0].collect('ubisoft', 25), 'UPSTREAM_TIMEOUT')
    assert len(source.tokens_seen) == 3


async def test_exhausted_mixed_failures_report_upstream_error():
    source = ScriptedSource(timeout_error(), network_error(), network_error())
    await expect_code(build(source)[0].collect('ubisoft', 25), 'UPSTREAM_ERROR')


async def test_an_auth_failure_refreshes_the_token_once_and_resends():
    tokens = FakeTokens()
    source = ScriptedSource(AppError('UPSTREAM_AUTH'), [make_post('t3_a')])
    await build(source, tokens=tokens)[0].collect('ubisoft', 25)
    assert tokens.rejected == ['token-1']
    assert source.tokens_seen == ['token-1', 'token-2']


async def test_a_second_auth_failure_gives_up():
    source = ScriptedSource(AppError('UPSTREAM_AUTH'), AppError('UPSTREAM_AUTH'))
    await expect_code(build(source)[0].collect('ubisoft', 25), 'UPSTREAM_AUTH')
    assert len(source.tokens_seen) == 2


async def test_a_rate_limit_is_not_retried_and_keeps_the_wait():
    source = ScriptedSource(AppError('RATE_LIMITED', retry_after_seconds=12))
    error = await expect_code(build(source)[0].collect('ubisoft', 25), 'RATE_LIMITED')
    assert error.retry_after_seconds == 12
    assert len(source.tokens_seen) == 1


async def test_the_deadline_stops_a_hanging_reddit():
    source = ScriptedSource('hang', 'hang', 'hang')
    loop = asyncio.get_running_loop()
    started = loop.time()
    await expect_code(
        build(source, deadline_seconds=0.1)[0].collect('ubisoft', 25), 'UPSTREAM_TIMEOUT'
    )
    assert loop.time() - started < 1


async def test_a_retry_whose_backoff_would_pass_the_deadline_is_skipped():
    source = ScriptedSource(network_error(), [make_post('t3_a')])
    collector, sleeps = build(source, deadline_seconds=0.2)
    await expect_code(collector.collect('ubisoft', 25), 'UPSTREAM_ERROR')
    assert sleeps == []


@pytest.mark.parametrize('code', list(ERROR_TABLE))
async def test_auto_retry_matches_the_error_table(code):
    source = ScriptedSource(AppError(code), AppError(code), AppError(code))
    await expect_code(build(source)[0].collect('ubisoft', 25), code)
    expected = 2 if code == 'UPSTREAM_AUTH' else 3 if ERROR_TABLE[code].auto_retry else 1
    assert len(source.tokens_seen) == expected


# FixtureCollector and factory

SAMPLES = [
    SamplePost(
        key='one',
        title='First',
        author='alice',
        comment_count=3,
        score=10,
        minutes_ago=5,
        preview_text='Hello',
        flair='Question',
    ),
    SamplePost(
        key='two',
        title='Second',
        author=None,
        comment_count=0,
        score=-1,
        minutes_ago=90,
        preview_text=None,
        flair=None,
    ),
]


def fixture_collector():
    return FixtureCollector(SAMPLES, FakeClock('2026-10-29T12:00:00.000Z'))


async def test_fixture_posts_belong_to_the_requested_subreddit():
    posts = await fixture_collector().collect('ubisoft', 25)
    assert posts[0].model_dump() == {
        'id': 't3_fx_ubisoft_one',
        'title': 'First',
        'author': 'alice',
        'comment_count': 3,
        'score': 10,
        'created_at': '2026-10-29T11:55:00.000Z',
        'permalink': 'https://www.reddit.com/r/ubisoft/comments/fx_ubisoft_one/',
        'subreddit': 'ubisoft',
        'preview_text': 'Hello',
        'flair': 'Question',
    }
    assert posts[1].author is None


async def test_fixture_collector_respects_the_limit_and_the_empty_name():
    assert len(await fixture_collector().collect('ubisoft', 1)) == 1
    assert await fixture_collector().collect('empty', 25) == []


@pytest.mark.parametrize(
    ('term', 'code'),
    [
        ('notfound', 'NOT_FOUND_SUBREDDIT'),
        ('ratelimited', 'RATE_LIMITED'),
        ('broken', 'UPSTREAM_ERROR'),
        ('timeout', 'UPSTREAM_TIMEOUT'),
    ],
)
async def test_fixture_collector_simulates_failures(term, code):
    await expect_code(fixture_collector().collect(term, 25), code)


async def test_fixture_collector_loads_the_bundled_sample_file():
    posts = await FixtureCollector.from_file(DEFAULT_SAMPLE_FILE, FakeClock()).collect(
        'ubisoft', 25
    )
    assert len(posts) >= 5
    assert all(p.permalink.startswith('https://www.reddit.com/r/ubisoft/') for p in posts)


def test_factory_picks_the_fixture_collector_only_in_fixture_mode():
    deps = {'clock': FakeClock(), 'logger': make_logger()}
    assert isinstance(
        create_collector(load_config({'COLLECTOR_MODE': 'fixture'}), **deps), FixtureCollector
    )
    assert isinstance(create_collector(load_config({}), **deps), RedditCollector)


def test_live_mode_wires_the_real_reddit_collector():
    from app.collector.reddit.mobile_api import MobileListingSource

    collector = create_collector(load_config({}), clock=FakeClock(), logger=make_logger())
    assert isinstance(collector, RedditCollector)
    # Built with the real mobile listing source; no network happens at construction.
    assert isinstance(collector._source, MobileListingSource)
