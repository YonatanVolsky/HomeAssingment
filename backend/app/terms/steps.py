"""Building blocks for term protocols.

Each step does one transformation, `str -> str`, or rejects the term with INVALID_TERM.
Steps know nothing about each other; a protocol (see presets.py) puts them in order.
"""

import re
from urllib.parse import urlparse

from app.errors import AppError
from app.terms.normalizer import Step

_URL_LIKE = re.compile(r'^(https?://)?([a-z0-9-]+\.)*reddit\.com(/|$)', re.IGNORECASE)
_HAS_SCHEME = re.compile(r'^https?://', re.IGNORECASE)
_SUBREDDIT_PATH = re.compile(r'^/r/([^/]+)', re.IGNORECASE)
_R_PREFIX = re.compile(r'^/?r/', re.IGNORECASE)


def trim(text: str) -> str:
    return text.strip()


def extract_reddit_link(text: str) -> str:
    """For a reddit.com link, the segment after /r/; any other text passes through unchanged."""
    if not _URL_LIKE.match(text):
        return text
    url = text if _HAS_SCHEME.match(text) else f'https://{text}'
    match = _SUBREDDIT_PATH.match(urlparse(url).path)
    if match is None:
        raise AppError('INVALID_TERM')
    return match.group(1)


def strip_r_prefix(text: str) -> str:
    return _R_PREFIX.sub('', text, count=1)


def strip_trailing_slash(text: str) -> str:
    return text.removesuffix('/')


def require_pattern(pattern: str) -> Step:
    """A step that rejects the term unless all of it matches `pattern`."""
    compiled = re.compile(pattern)

    def require(text: str) -> str:
        if not compiled.fullmatch(text):
            raise AppError('INVALID_TERM')
        return text

    return require


def lowercase(text: str) -> str:
    return text.lower()
