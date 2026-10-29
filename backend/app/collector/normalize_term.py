import re
from urllib.parse import urlparse

from app.errors import AppError

# Reddit's documented rule is 3-21 characters, but a few legacy subreddits (r/de) have 2.
# Only names that can never be valid are rejected here; Reddit decides whether one exists.
_SUBREDDIT_NAME = re.compile(r'[A-Za-z0-9_]{2,21}')
_URL_LIKE = re.compile(r'^(https?://)?([a-z0-9-]+\.)*reddit\.com(/|$)', re.IGNORECASE)


def normalize_term(term: str) -> str:
    """Returns the bare lowercase subreddit name, or raises INVALID_TERM."""
    name = _extract_name(term.strip())
    if name is None or not _SUBREDDIT_NAME.fullmatch(name):
        raise AppError('INVALID_TERM')
    return name.lower()


def _extract_name(term: str) -> str | None:
    if _URL_LIKE.match(term):
        url = term if re.match(r'^https?://', term, re.IGNORECASE) else f'https://{term}'
        match = re.match(r'^/r/([^/]+)', urlparse(url).path, re.IGNORECASE)
        return match.group(1) if match else None
    return re.sub(r'/$', '', re.sub(r'^/?r/', '', term, flags=re.IGNORECASE))
