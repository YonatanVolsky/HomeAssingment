import json
from pathlib import Path

import pytest

from app.collector.reddit.mobile_api import (
    GQL_URL,
    SUBREDDIT_FEED_HASH,
    TOKEN_URL,
    HttpResponse,
    MobileListingSource,
    create_anonymous_token_fetcher,
)
from app.config import load_config
from app.errors import AppError

pytestmark = pytest.mark.anyio

REAL = (Path(__file__).parent / 'fixtures' / 'listing-new-ok.json').read_text()
CONFIG = load_config({})


class RecordingTransport:
    """Records the last request and returns a canned response."""

    def __init__(self, response: HttpResponse):
        self.response = response
        self.calls = []

    async def post(self, url, headers, body, timeout_s):
        self.calls.append({'url': url, 'headers': headers, 'body': body, 'timeout': timeout_s})
        return self.response


def token_response(**over):
    body = {'access_token': 'anon-token-xyz', 'expires_in': 86399, 'token_type': 'bearer'}
    body.update(over)
    return HttpResponse(200, {}, json.dumps(body))


async def test_token_fetcher_builds_the_anonymous_token_request():
    transport = RecordingTransport(token_response())
    fetch = create_anonymous_token_fetcher(CONFIG, transport=transport)

    token = await fetch()

    assert token.access_token == 'anon-token-xyz'
    assert token.expires_in_seconds == 86399
    call = transport.calls[0]
    assert call['url'] == TOKEN_URL
    assert call['headers']['Authorization'].startswith('Basic ')
    assert json.loads(call['body'])['scopes'] == ['*', 'email', 'pii']
    assert 'Reddit/Version' in call['headers']['User-Agent']


async def test_token_fetcher_maps_a_rate_limit():
    transport = RecordingTransport(HttpResponse(429, {'retry-after': '12'}, 'slow down'))
    fetch = create_anonymous_token_fetcher(CONFIG, transport=transport)

    with pytest.raises(AppError) as raised:
        await fetch()
    assert raised.value.code == 'RATE_LIMITED'
    assert raised.value.retry_after_seconds == 12


async def test_listing_source_builds_the_feed_request_and_parses_posts():
    transport = RecordingTransport(HttpResponse(200, {}, REAL))
    source = MobileListingSource(CONFIG, transport=transport)

    posts = await source.fetch_new_posts('ubisoft', 25, 'anon-token-xyz')

    assert posts[0].id == 't3_1wcg6wx'
    call = transport.calls[0]
    assert call['url'] == GQL_URL
    assert call['headers']['Authorization'] == 'Bearer anon-token-xyz'
    assert call['headers']['x-apollo-operation-name'] == 'SubredditFeedElements'
    body = json.loads(call['body'])
    assert body['variables']['subredditName'] == 'ubisoft'
    assert body['variables']['sort'] == 'NEW'
    assert body['extensions']['persistedQuery']['sha256Hash'] == SUBREDDIT_FEED_HASH


async def test_listing_source_respects_the_limit():
    transport = RecordingTransport(HttpResponse(200, {}, REAL))
    source = MobileListingSource(CONFIG, transport=transport)
    assert len(await source.fetch_new_posts('ubisoft', 3, 't')) == 3


@pytest.mark.parametrize(
    ('status', 'code'),
    [(403, 'UPSTREAM_AUTH'), (404, 'NOT_FOUND_SUBREDDIT'), (500, 'UPSTREAM_ERROR')],
)
async def test_listing_source_classifies_http_errors(status, code):
    transport = RecordingTransport(HttpResponse(status, {}, '<html>blocked</html>'))
    source = MobileListingSource(CONFIG, transport=transport)

    with pytest.raises(AppError) as raised:
        await source.fetch_new_posts('ubisoft', 25, 't')
    assert raised.value.code == code


async def test_listing_source_raises_contract_error_on_non_json():
    transport = RecordingTransport(HttpResponse(200, {'content-type': 'text/html'}, '<html>'))
    source = MobileListingSource(CONFIG, transport=transport)

    with pytest.raises(AppError) as raised:
        await source.fetch_new_posts('ubisoft', 25, 't')
    assert raised.value.code == 'CONTRACT_ERROR'


async def test_listing_source_reports_a_missing_subreddit_sent_as_http_200():
    body = json.dumps({'data': {'postFeed': None}, 'extensions': {'traceID': 'x'}})
    transport = RecordingTransport(HttpResponse(200, {}, body))
    source = MobileListingSource(CONFIG, transport=transport)

    with pytest.raises(AppError) as raised:
        await source.fetch_new_posts('zqxvbnmlkjqw', 25, 't')
    assert raised.value.code == 'NOT_FOUND_SUBREDDIT'
    assert raised.value.retryable is False
