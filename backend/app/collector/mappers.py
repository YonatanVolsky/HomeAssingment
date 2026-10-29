"""Pure conversions from Reddit's raw values to the Post contract."""

import math
import re
from datetime import UTC, datetime
from urllib.parse import urljoin, urlparse, urlunparse

from app.clock import iso
from app.errors import AppError

PREVIEW_MAX = 300
# Epoch values below this are seconds; above it, milliseconds (year 5138 in seconds).
_MS_THRESHOLD = 1e11
# Reddit pads empty paragraphs with zero-width spaces, raw or as an HTML entity.
_ZERO_WIDTH = re.compile('&#x200B;|​', re.IGNORECASE)
_MISSING_AUTHORS = {'', '[deleted]', '[removed]'}


def _contract_error(reason: str) -> AppError:
    return AppError('CONTRACT_ERROR', cause=ValueError(reason))


def to_iso_utc(value: object) -> str:
    """Accepts epoch seconds, epoch milliseconds or an ISO string; returns ISO UTC."""
    moment: datetime | None = None
    is_number = isinstance(value, int | float) and not isinstance(value, bool)
    is_numeric_text = isinstance(value, str) and re.fullmatch(r'\d+(\.\d+)?', value) is not None
    if is_number or is_numeric_text:
        moment = _from_epoch(float(value))  # type: ignore[arg-type]
    elif isinstance(value, str):
        try:
            moment = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError:
            moment = None
        if moment is not None and moment.tzinfo is None:
            moment = moment.replace(tzinfo=UTC)
    if moment is None:
        raise _contract_error(f'invalid timestamp of type {type(value).__name__}')
    return iso(moment)


def _from_epoch(value: float) -> datetime | None:
    if not math.isfinite(value) or value < 0:
        return None
    seconds = value / 1000 if value >= _MS_THRESHOLD else value
    return datetime.fromtimestamp(seconds, UTC)


def to_absolute_permalink(value: object) -> str:
    """Absolute https reddit.com URL without query or fragment, or CONTRACT_ERROR."""
    if not isinstance(value, str) or value == '':
        raise _contract_error('missing permalink')
    url = urlparse(urljoin('https://www.reddit.com', value))
    host = (url.hostname or '').lower()
    is_reddit = host == 'reddit.com' or host.endswith('.reddit.com')
    if not is_reddit or url.scheme not in ('http', 'https'):
        raise _contract_error('permalink is not a reddit.com URL')
    return urlunparse(('https', url.netloc, url.path, '', '', ''))


def truncate_preview(value: object) -> str | None:
    """Plain-text preview of at most 300 characters, or None when there is no text."""
    if not isinstance(value, str):
        return None
    text = re.sub(r'\s+', ' ', _strip_markup(value)).strip()
    if text == '':
        return None
    if len(text) <= PREVIEW_MAX:
        return text
    cut = text[: PREVIEW_MAX - 1]
    last_space = cut.rfind(' ')
    base = cut[:last_space] if last_space > PREVIEW_MAX // 2 else cut
    return f'{base.rstrip()}…'


def _strip_markup(text: str) -> str:
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', text)
    text = re.sub(r'^#{1,6}\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'^>\s?', '', text, flags=re.MULTILINE)
    text = re.sub(r'(\*\*|__|~~)(.+?)\1', r'\2', text)
    text = re.sub(r'(^|\W)[*_](\S(?:.*?\S)?)[*_](?=\W|$)', r'\1\2', text)
    text = re.sub(r'`([^`]*)`', r'\1', text)
    text = _ZERO_WIDTH.sub('', text)
    for entity, char in (
        ('&nbsp;', ' '),
        ('&lt;', '<'),
        ('&gt;', '>'),
        ('&quot;', '"'),
        ('&#39;', "'"),
        ('&amp;', '&'),
    ):
        text = text.replace(entity, char)
    return text


def map_author(value: object) -> str | None:
    if isinstance(value, str) and value.strip() not in _MISSING_AUTHORS:
        return value.strip()
    return None


def map_flair(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None
