import functools
import logging
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import ParamSpec, TypeVar

from app.clock import Clock, iso
from app.contracts import Post
from app.db.connection import transaction
from app.errors import AppError, ErrorCode

P = ParamSpec('P')
R = TypeVar('R')


@dataclass(frozen=True)
class StoredCollection:
    """A successful collection as stored. The service decides `source` (live or cache)."""

    id: int
    term: str
    post_count: int
    collected_at: str


def _db_errors(method: Callable[P, R]) -> Callable[P, R]:
    """Turns any SQLite failure into DB_ERROR; the original stays as the cause for logs only."""

    @functools.wraps(method)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return method(*args, **kwargs)
        except sqlite3.Error as cause:
            raise AppError('DB_ERROR', cause=cause) from cause

    return wrapper


_UPSERT_POST = """
INSERT INTO posts (reddit_id, title, author, comment_count, score, created_at, permalink,
                   subreddit, preview_text, flair, first_seen_at, last_seen_at)
VALUES (:reddit_id, :title, :author, :comment_count, :score, :created_at, :permalink,
        :subreddit, :preview_text, :flair, :seen_at, :seen_at)
ON CONFLICT (reddit_id) DO UPDATE SET
  title = excluded.title,
  author = excluded.author,
  comment_count = excluded.comment_count,
  score = excluded.score,
  permalink = excluded.permalink,
  subreddit = excluded.subreddit,
  preview_text = excluded.preview_text,
  flair = excluded.flair,
  last_seen_at = excluded.last_seen_at
RETURNING id
"""

_INSERT_COLLECTION = """
INSERT INTO collections (term, status, post_count, error_code, started_at, finished_at)
VALUES (:term, :status, :post_count, :error_code, :started_at, :finished_at)
RETURNING id
"""

_SELECT_FEED = """
SELECT p.reddit_id, p.title, p.author, p.comment_count, p.score, p.created_at, p.permalink,
       p.subreddit, p.preview_text, p.flair
FROM collection_posts cp
JOIN posts p ON p.id = cp.post_id
WHERE cp.collection_id = ?
ORDER BY p.created_at DESC, p.reddit_id ASC
"""

_SELECT_LATEST_SUCCESS = """
SELECT id, term, post_count, finished_at
FROM collections
WHERE term = ? AND status = 'success' AND finished_at >= ?
ORDER BY finished_at DESC, id DESC
LIMIT 1
"""

_EPOCH = '1970-01-01T00:00:00.000Z'


class Repository:
    """All SQL lives here. Every query uses bound parameters."""

    def __init__(self, db: sqlite3.Connection, clock: Clock, logger: logging.Logger) -> None:
        self._db = db
        self._clock = clock
        self._logger = logger

    @_db_errors
    def record_success(
        self, term: str, posts: list[Post], started_at: datetime
    ) -> StoredCollection:
        """Stores a successful run atomically: posts, the run, and its links."""
        finished_at = iso(self._clock.now())
        unique = list({post.id: post for post in posts}.values())
        with transaction(self._db):
            collection_id = self._db.execute(
                _INSERT_COLLECTION,
                {
                    'term': term,
                    'status': 'success',
                    'post_count': len(unique),
                    'error_code': None,
                    'started_at': iso(started_at),
                    'finished_at': finished_at,
                },
            ).fetchone()[0]
            for position, post in enumerate(unique):
                post_id = self._db.execute(
                    _UPSERT_POST, {**_post_row(post), 'seen_at': finished_at}
                ).fetchone()[0]
                self._db.execute(
                    'INSERT OR IGNORE INTO collection_posts (collection_id, post_id, position) '
                    'VALUES (?, ?, ?)',
                    (collection_id, post_id, position),
                )
        return StoredCollection(collection_id, term, len(unique), finished_at)

    def record_failure(self, term: str, error_code: ErrorCode, started_at: datetime) -> None:
        """Records a failed attempt. Never raises, so a failed write cannot hide the real error."""
        try:
            self._db.execute(
                _INSERT_COLLECTION,
                {
                    'term': term,
                    'status': 'failed',
                    'post_count': 0,
                    'error_code': error_code,
                    'started_at': iso(started_at),
                    'finished_at': iso(self._clock.now()),
                },
            ).fetchone()
        except sqlite3.Error:
            self._logger.exception('could not record failed collection for %s', term)

    @_db_errors
    def get_latest_success(self, term: str) -> StoredCollection | None:
        return self._latest_since(term, _EPOCH)

    @_db_errors
    def get_fresh_success(self, term: str, ttl_seconds: int) -> StoredCollection | None:
        """Latest success finished within `ttl_seconds` of now; a TTL of 0 always gives None."""
        if ttl_seconds <= 0:
            return None
        since = iso(self._clock.now() - timedelta(seconds=ttl_seconds))
        return self._latest_since(term, since)

    @_db_errors
    def get_feed(self, collection_id: int) -> list[Post]:
        rows = self._db.execute(_SELECT_FEED, (collection_id,)).fetchall()
        return [_row_to_post(row) for row in rows]

    @_db_errors
    def ping(self) -> None:
        self._db.execute('SELECT 1').fetchone()

    def _latest_since(self, term: str, since: str) -> StoredCollection | None:
        row = self._db.execute(_SELECT_LATEST_SUCCESS, (term, since)).fetchone()
        if row is None:
            return None
        return StoredCollection(row['id'], row['term'], row['post_count'], row['finished_at'])


def _post_row(post: Post) -> dict[str, object]:
    return {
        'reddit_id': post.id,
        'title': post.title,
        'author': post.author,
        'comment_count': post.comment_count,
        'score': post.score,
        'created_at': post.created_at,
        'permalink': post.permalink,
        'subreddit': post.subreddit,
        'preview_text': post.preview_text,
        'flair': post.flair,
    }


def _row_to_post(row: sqlite3.Row) -> Post:
    return Post(
        id=row['reddit_id'],
        title=row['title'],
        author=row['author'],
        comment_count=row['comment_count'],
        score=row['score'],
        created_at=row['created_at'],
        permalink=row['permalink'],
        subreddit=row['subreddit'],
        preview_text=row['preview_text'],
        flair=row['flair'],
    )
