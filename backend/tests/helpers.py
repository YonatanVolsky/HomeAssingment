import logging
from datetime import UTC, datetime, timedelta

from app.contracts import Post


def make_post(post_id: str, **overrides) -> Post:
    fields = {
        'id': post_id,
        'title': f'Post {post_id}',
        'author': 'someone',
        'comment_count': 0,
        'score': 1,
        'created_at': '2026-10-29T10:00:00.000Z',
        'permalink': f'https://www.reddit.com/r/ubisoft/comments/{post_id}/',
        'subreddit': 'ubisoft',
        'preview_text': None,
        'flair': None,
    }
    fields.update(overrides)
    return Post(**fields)


class FakeClock:
    """A clock that only moves when told to."""

    def __init__(self, iso: str = '2026-10-29T12:00:00.000Z') -> None:
        self.current = datetime.fromisoformat(iso).astimezone(UTC)

    def now(self) -> datetime:
        return self.current

    def advance(self, seconds: float) -> None:
        self.current += timedelta(seconds=seconds)


def make_logger() -> logging.Logger:
    return logging.getLogger('test')
