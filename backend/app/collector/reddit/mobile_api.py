"""The Reddit mobile app's anonymous token and subreddit-listing requests.

Reverse-engineered from a traffic capture of Reddit for Android 2024.24.0; the full spec,
including why this is the app's own traffic and not the official API, is in
docs/reddit-mobile-request.md.

Reddit's edge rejects a default Python HTTP client (returns 403 before the token is checked),
so the default transport uses curl_cffi with an Android-client TLS fingerprint, the same thing
the app presents at the transport layer. The transport is injected, so tests run offline.
"""

import asyncio
import json
import uuid
from dataclasses import dataclass
from typing import Protocol

from app.collector.classify import classify_network_error, classify_status
from app.collector.reddit.parse_listing import parse_listing
from app.collector.token_provider import FetchedToken, TokenFetcher
from app.config import Config
from app.contracts import Post
from app.errors import AppError

APP_VERSION = '2024.24.0'
APP_BUILD = '1675730'
USER_AGENT = f'Reddit/Version {APP_VERSION}/Build {APP_BUILD}/Android 13'
# Public client id shipped in every copy of the app (Basic base64("ohXpoqrZYub1kg:")).
# Not a secret: it is the app's installed-client identifier, sent by every anonymous user.
CLIENT_AUTH = 'Basic b2hYcG9xclpZdWIxa2c6'

TOKEN_URL = 'https://www.reddit.com/auth/v2/oauth/access-token/loid'
GQL_URL = 'https://gql-fed.reddit.com/'
OPERATION_NAME = 'SubredditFeedElements'
SUBREDDIT_FEED_HASH = '5f8ce513df609c3b3da05d797dbff3fa042f7761380747ee486e20e6f2aafccb'

# TLS/HTTP-2 fingerprint of a real Android client; the exact UA is still the app's, above.
_IMPERSONATE = 'chrome_android'


@dataclass(frozen=True)
class HttpResponse:
    status: int
    headers: dict[str, str]
    text: str


class Transport(Protocol):
    async def post(
        self, url: str, headers: dict[str, str], body: str, timeout_s: float
    ) -> HttpResponse: ...


class CurlCffiTransport:
    """Default transport: curl_cffi with an Android-client fingerprint, run off the event loop."""

    async def post(
        self, url: str, headers: dict[str, str], body: str, timeout_s: float
    ) -> HttpResponse:
        try:
            response = await asyncio.to_thread(self._post, url, headers, body, timeout_s)
        except Exception as error:  # curl_cffi network/timeout errors
            raise classify_network_error(error) from error
        return response

    @staticmethod
    def _post(url: str, headers: dict[str, str], body: str, timeout_s: float) -> HttpResponse:
        from curl_cffi import requests

        r = requests.post(
            url,
            headers=headers,
            data=body.encode(),
            impersonate=_IMPERSONATE,
            timeout=timeout_s,
        )
        return HttpResponse(r.status_code, dict(r.headers), r.text)


def _timeout_seconds(config: Config) -> float:
    return config.request_timeout_ms / 1000


def create_anonymous_token_fetcher(
    config: Config, transport: Transport | None = None
) -> TokenFetcher:
    transport = transport or CurlCffiTransport()
    headers = {
        'Authorization': CLIENT_AUTH,
        'User-Agent': USER_AGENT,
        'Content-Type': 'application/json; charset=UTF-8',
        'client-vendor-id': str(uuid.uuid4()),
    }
    body = json.dumps({'scopes': ['*', 'email', 'pii']})

    async def fetch() -> FetchedToken:
        response = await transport.post(TOKEN_URL, headers, body, _timeout_seconds(config))
        error = classify_status(response.status, response.headers)
        if error is not None:
            raise error
        try:
            data = json.loads(response.text)
            return FetchedToken(str(data['access_token']), int(data['expires_in']))
        except (ValueError, KeyError, TypeError) as cause:
            raise AppError('CONTRACT_ERROR', cause=cause) from cause

    return fetch


class MobileListingSource:
    def __init__(self, config: Config, transport: Transport | None = None) -> None:
        self._config = config
        self._transport = transport or CurlCffiTransport()
        # A device id is stable for this process, like one app install.
        self._device_id = str(uuid.uuid4())

    async def fetch_new_posts(self, subreddit: str, limit: int, token: str) -> list[Post]:
        headers = {
            'Authorization': f'Bearer {token}',
            'User-Agent': USER_AGENT,
            'Content-Type': 'application/json; charset=utf-8',
            'x-apollo-operation-name': OPERATION_NAME,
            'x-reddit-device-id': self._device_id,
            'client-vendor-id': self._device_id,
        }
        body = json.dumps(self._feed_body(subreddit))
        response = await self._transport.post(
            GQL_URL, headers, body, _timeout_seconds(self._config)
        )

        error = classify_status(response.status, response.headers)
        if error is not None:
            raise error
        try:
            data = json.loads(response.text)
        except ValueError as cause:
            # The edge block page and any non-JSON body land here.
            raise AppError('CONTRACT_ERROR', cause=cause) from cause
        return parse_listing(data, limit)

    def _feed_body(self, subreddit: str) -> dict:
        return {
            'operationName': OPERATION_NAME,
            'variables': {
                'subredditName': subreddit,
                'sort': 'NEW',
                'optedIn': True,
                'includePostStats': True,
                'includeAwards': True,
                'includeStillMediaAltText': True,
                'includeCurrentUserAwards': False,
                'includeSubredditInPosts': False,
                'includeMediaAuth': False,
                'adContext': {'layout': 'CARD'},
                'feedContext': {'experimentOverrides': []},
                'feedFilters': {},
                'forceAds': {},
            },
            'extensions': {'persistedQuery': {'version': 1, 'sha256Hash': SUBREDDIT_FEED_HASH}},
        }


def create_mobile_listing_source(config: Config) -> MobileListingSource:
    return MobileListingSource(config)
