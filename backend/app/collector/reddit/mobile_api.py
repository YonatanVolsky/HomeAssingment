"""The Reddit mobile app's token and listing requests.

Filled in from the traffic capture (docs/reddit-mobile-request.md). Until then live mode
explains itself instead of pretending to work.
"""

from app.collector.reddit_collector import ListingSource
from app.collector.token_provider import FetchedToken, TokenFetcher
from app.config import Config
from app.contracts import Post
from app.errors import AppError

LIVE_COLLECTION_AVAILABLE = False
"""False until the captured requests replace the placeholders below."""


def _not_captured_yet() -> AppError:
    return AppError(
        'UPSTREAM_ERROR',
        'Live Reddit collection is not available yet. '
        'Run with COLLECTOR_MODE=fixture for sample data.',
        auto_retry=False,
        retryable=False,
    )


def create_anonymous_token_fetcher(_config: Config) -> TokenFetcher:
    async def fetch() -> FetchedToken:
        return FetchedToken('placeholder', 3600)

    return fetch


class _NotCapturedSource:
    async def fetch_new_posts(self, subreddit: str, limit: int, token: str) -> list[Post]:
        raise _not_captured_yet()


def create_mobile_listing_source(_config: Config) -> ListingSource:
    return _NotCapturedSource()
