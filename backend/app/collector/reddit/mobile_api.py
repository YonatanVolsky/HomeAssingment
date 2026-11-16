"""The Reddit mobile app's anonymous token and subreddit-listing requests.

Reverse-engineered from a traffic capture of Reddit for Android 2024.24.0; the full spec,
including why this is the app's own traffic and not the official API, is in
docs/reddit-mobile-request.md.

Every call to Reddit goes out over a direct HTTP/2 connection that presents the exact
TLS (JA3) and HTTP/2 (Akamai) fingerprint the Android app was captured sending, rather than
a generic browser profile. Headers are sent in the app's order, lowercase, and curl_cffi is
told not to add any of its own. The transport is injected, so tests run offline.

Fingerprint source: akamai_fp.py capture of gql-fed.reddit.com (feed requests), 2026-11-16.
"""

import asyncio
import json
import uuid
import warnings
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

# --- Captured fingerprint of the Reddit Android app (OkHttp 5 on Conscrypt/BoringSSL) -------
# JA3 of a fresh (non-resumed) handshake. The trailing 21 is the padding extension, which
# BoringSSL adds on its own; curl_cffi warns about it, so that warning is silenced below.
APP_JA3 = (
    '771,'
    '4865-4866-4867-49195-49199-49196-49200-52393-52392-49171-49172-156-157-47-53,'
    '0-23-65281-10-11-35-16-5-13-51-45-43-21,'
    '29-23-24,'
    '0'
)
APP_JA3_HASH = '1d714db2228763eab228fc28ce7f8e4f'
# SETTINGS | WINDOW_UPDATE | PRIORITY | pseudo-header order
APP_AKAMAI = '4:16777216|16711681|0|m,p,a,s'
APP_EXTRA_FP = {
    'tls_signature_algorithms': [
        'ecdsa_secp256r1_sha256',
        'rsa_pss_rsae_sha256',
        'rsa_pkcs1_sha256',
        'ecdsa_secp384r1_sha384',
        'rsa_pss_rsae_sha384',
        'rsa_pkcs1_sha384',
        'rsa_pss_rsae_sha512',
        'rsa_pkcs1_sha512',
        'rsa_pkcs1_sha1',
    ],
    'tls_min_version': 4,  # CurlSslVersion.TLSv1_0 (app offers TLS 1.0-1.3)
    'tls_grease': False,
    'tls_permute_extensions': False,
    'http2_no_priority': True,  # OkHttp sends no HEADERS priority
}
APP_ACCEPT_ENCODING = 'gzip'

warnings.filterwarnings('ignore', message=r'Padding\(21\) extension found in ja3 string')


@dataclass(frozen=True)
class HttpResponse:
    status: int
    headers: dict[str, str]
    text: str


class Transport(Protocol):
    async def post(
        self, url: str, headers: dict[str, str], body: str, timeout_s: float
    ) -> HttpResponse: ...


class AppFingerprintTransport:
    """Default transport: direct HTTP/2 with the Reddit app's captured TLS + HTTP/2 fingerprint.

    Uses curl_cffi's native async session (no worker threads) and keeps the connection pool
    for the life of the transport, the way the app reuses its OkHttp connections.
    """

    def __init__(self) -> None:
        self._session = None
        self._loop: asyncio.AbstractEventLoop | None = None

    def _get_session(self):
        from curl_cffi import CurlOpt
        from curl_cffi.requests import AsyncSession

        loop = asyncio.get_running_loop()
        if self._session is None or self._loop is not loop:
            # curl_cffi only enables status_request (ext 5) for its built-in browser
            # profiles; with a raw ja3= it must be switched on or JA3 won't match.
            self._session = AsyncSession(curl_options={CurlOpt.TLS_STATUS_REQUEST: 1})
            self._loop = loop
        return self._session

    async def post(
        self, url: str, headers: dict[str, str], body: str, timeout_s: float
    ) -> HttpResponse:
        try:
            r = await self._get_session().post(
                url,
                headers=headers,
                data=body.encode(),
                ja3=APP_JA3,
                akamai=APP_AKAMAI,
                extra_fp=APP_EXTRA_FP,
                accept_encoding=APP_ACCEPT_ENCODING,
                default_headers=False,
                timeout=timeout_s,
            )
        except Exception as error:  # curl_cffi network/timeout errors
            raise classify_network_error(error) from error
        return HttpResponse(r.status_code, dict(r.headers), r.text)

    async def aclose(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None
            self._loop = None


# Backwards-compatible name for callers that import the old transport.
CurlCffiTransport = AppFingerprintTransport


def _timeout_seconds(config: Config) -> float:
    return config.request_timeout_ms / 1000


def create_anonymous_token_fetcher(
    config: Config, transport: Transport | None = None
) -> TokenFetcher:
    transport = transport or AppFingerprintTransport()
    # Same relative order as the app's token request.
    headers = {
        'authorization': CLIENT_AUTH,
        'user-agent': USER_AGENT,
        'content-type': 'application/json; charset=UTF-8',
        'accept-encoding': APP_ACCEPT_ENCODING,
        'client-vendor-id': str(uuid.uuid4()),
    }
    body = json.dumps({'scopes': ['*', 'email', 'pii']})

    async def fetch() -> FetchedToken:
        response = await transport.post(TOKEN_URL, headers, body, _timeout_seconds(config))
        error = classify_status(response.status, response.headers, response.text)
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
        self._transport = transport or AppFingerprintTransport()
        # A device id is stable for this process, like one app install.
        self._device_id = str(uuid.uuid4())

    async def fetch_new_posts(self, subreddit: str, limit: int, token: str) -> list[Post]:
        # Same relative order as the app's GraphQL requests.
        headers = {
            'x-apollo-operation-id': SUBREDDIT_FEED_HASH,
            'x-apollo-operation-name': OPERATION_NAME,
            'accept': 'multipart/mixed; deferSpec=20220824, application/json',
            'authorization': f'Bearer {token}',
            'client-vendor-id': self._device_id,
            'x-reddit-device-id': self._device_id,
            'user-agent': USER_AGENT,
            'content-type': 'application/json; charset=utf-8',
            'accept-encoding': APP_ACCEPT_ENCODING,
        }
        body = json.dumps(self._feed_body(subreddit))
        response = await self._transport.post(
            GQL_URL, headers, body, _timeout_seconds(self._config)
        )

        error = classify_status(response.status, response.headers, response.text)
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
