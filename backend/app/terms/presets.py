"""The term protocols a deployment can choose with TERM_PROTOCOL."""

from collections.abc import Mapping
from types import MappingProxyType

from app.terms.normalizer import TermProtocol
from app.terms.steps import (
    extract_reddit_link,
    lowercase,
    require_pattern,
    strip_r_prefix,
    strip_trailing_slash,
    trim,
)

# Reddit's documented rule is 3-21 characters, but a few legacy subreddits (r/de) have 2.
# Only names that can never be valid are rejected here; Reddit decides whether one exists.
SUBREDDIT_NAME = r'[A-Za-z0-9_]{2,21}'

DEFAULT_PRESET = 'reddit-subreddit'

PRESETS: Mapping[str, TermProtocol] = MappingProxyType(
    {
        # A subreddit name, r/name, /r/name/ or a reddit.com link to it -> the lowercase name.
        'reddit-subreddit': TermProtocol(
            name='reddit-subreddit',
            steps=(
                trim,
                extract_reddit_link,
                strip_r_prefix,
                strip_trailing_slash,
                require_pattern(SUBREDDIT_NAME),
                lowercase,
            ),
        ),
    }
)
