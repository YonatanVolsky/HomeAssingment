import httpx
import pytest

from app.collector.classify import classify_network_error, classify_status
from app.collector.mappers import (
    map_author,
    map_flair,
    to_absolute_permalink,
    to_iso_utc,
    truncate_preview,
)
from app.errors import AppError

# mappers


def contract_error(fn, *args):
    with pytest.raises(AppError) as raised:
        fn(*args)
    assert raised.value.code == 'CONTRACT_ERROR'


@pytest.mark.parametrize(
    'value',
    [
        1730000000,
        1730000000000,
        1730000000.5,
        '1730000000',
        '2024-10-27T03:33:20Z',
        '2024-10-27T05:33:20+02:00',
    ],
)
def test_to_iso_utc_converts_epoch_and_iso_values(value):
    assert to_iso_utc(value).startswith('2024-10-27T03:33:20')
    assert to_iso_utc(value).endswith('Z')


@pytest.mark.parametrize('value', ['not a date', None, float('nan'), -1, {}, True])
def test_to_iso_utc_rejects_bad_values(value):
    contract_error(to_iso_utc, value)


def test_relative_permalinks_get_the_reddit_host():
    assert (
        to_absolute_permalink('/r/ubisoft/comments/abc/title/')
        == 'https://www.reddit.com/r/ubisoft/comments/abc/title/'
    )


def test_absolute_permalinks_are_forced_to_https_without_query_or_fragment():
    assert (
        to_absolute_permalink('http://old.reddit.com/r/ubisoft/comments/abc/?utm_source=share#x')
        == 'https://old.reddit.com/r/ubisoft/comments/abc/'
    )


@pytest.mark.parametrize(
    'value',
    ['https://evil.com/r/x/', 'https://reddit.com.evil.com/r/x/', 'javascript:alert(1)', '', 42],
)
def test_permalinks_off_reddit_are_rejected(value):
    contract_error(to_absolute_permalink, value)


@pytest.mark.parametrize('value', [None, '', '   \n\t '])
def test_preview_is_none_without_text(value):
    assert truncate_preview(value) is None


def test_preview_collapses_whitespace_and_strips_markup():
    assert truncate_preview('Hello\n\n  world\t!') == 'Hello world !'
    assert (
        truncate_preview(
            '# Title\n> quoted **bold** _it_ [link](https://x.y) <b>tag</b> &amp; &#x200B;'
        )
        == 'Title quoted bold it link tag &'
    )


def test_preview_is_truncated_to_300_characters_on_a_word_boundary():
    preview = truncate_preview('word ' * 100)
    assert len(preview) <= 300
    assert preview.endswith('word…')
    assert truncate_preview('a' * 300) == 'a' * 300


@pytest.mark.parametrize('value', ['[deleted]', '[removed]', '', None])
def test_missing_authors_map_to_none(value):
    assert map_author(value) is None


def test_real_authors_and_flair_are_kept_trimmed():
    assert map_author('LazyGas7003') == 'LazyGas7003'
    assert map_flair('  Question ') == 'Question'
    assert map_flair('  ') is None
    assert map_flair(None) is None


# classify


@pytest.mark.parametrize('status', [200, 204, 299])
def test_success_statuses_are_not_errors(status):
    assert classify_status(status, {}) is None


@pytest.mark.parametrize(
    ('status', 'code', 'auto_retry'),
    [
        (401, 'UPSTREAM_AUTH', False),
        (403, 'UPSTREAM_AUTH', False),
        (404, 'NOT_FOUND_SUBREDDIT', False),
        (500, 'UPSTREAM_ERROR', True),
        (503, 'UPSTREAM_ERROR', True),
        (400, 'UPSTREAM_ERROR', False),
        (418, 'UPSTREAM_ERROR', False),
    ],
)
def test_error_statuses_are_classified(status, code, auto_retry):
    error = classify_status(status, {})
    assert (error.code, error.auto_retry) == (code, auto_retry)


@pytest.mark.parametrize(
    ('headers', 'seconds'),
    [({'retry-after': '17'}, 17), ({'x-ratelimit-reset': '42.0'}, 42), ({}, 30)],
)
def test_rate_limits_carry_the_wait_time(headers, seconds):
    error = classify_status(429, headers)
    assert (error.code, error.retry_after_seconds, error.auto_retry) == (
        'RATE_LIMITED',
        seconds,
        False,
    )


@pytest.mark.parametrize(
    ('exception', 'code'),
    [
        (httpx.ConnectTimeout('connect-detail-1'), 'UPSTREAM_TIMEOUT'),
        (httpx.ReadTimeout('read-detail-2'), 'UPSTREAM_TIMEOUT'),
        (httpx.ConnectError('dns-detail-3'), 'UPSTREAM_ERROR'),
        (httpx.RemoteProtocolError('socket-detail-4'), 'UPSTREAM_ERROR'),
    ],
)
def test_network_errors_are_auto_retried(exception, code):
    error = classify_network_error(exception)
    assert (error.code, error.auto_retry) == (code, True)
    assert error.__cause__ is exception
    assert str(exception) not in error.message


def test_app_errors_pass_through_unchanged():
    original = AppError('CONTRACT_ERROR')
    assert classify_network_error(original) is original
