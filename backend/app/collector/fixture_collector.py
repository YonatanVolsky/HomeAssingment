import json
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from app.clock import Clock, iso
from app.contracts import Post
from app.errors import AppError

DEFAULT_SAMPLE_FILE = Path(__file__).resolve().parents[2] / 'fixtures' / 'sample-posts.json'


class SamplePost(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, frozen=True)

    key: str = Field(pattern=r'^[a-z0-9_]+$')
    title: str = Field(min_length=1)
    author: str | None
    comment_count: int = Field(ge=0)
    score: int
    minutes_ago: float = Field(ge=0)
    preview_text: str | None
    flair: str | None


# Subreddit names that simulate an outcome, so every UI state can be shown offline.
_SIMULATED_FAILURES: dict[str, Callable[[], AppError]] = {
    'notfound': lambda: AppError('NOT_FOUND_SUBREDDIT'),
    'ratelimited': lambda: AppError('RATE_LIMITED', retry_after_seconds=30),
    'broken': lambda: AppError('UPSTREAM_ERROR'),
    'timeout': lambda: AppError('UPSTREAM_TIMEOUT'),
}


class FixtureCollector:
    """Offline sample data (COLLECTOR_MODE=fixture). Never calls Reddit."""

    def __init__(self, samples: list[SamplePost], clock: Clock) -> None:
        self._samples = samples
        self._clock = clock

    @classmethod
    def from_file(cls, path: Path, clock: Clock) -> 'FixtureCollector':
        raw = json.loads(path.read_text(encoding='utf-8'))
        return cls([SamplePost.model_validate(item) for item in raw], clock)

    async def collect(self, subreddit: str, limit: int) -> list[Post]:
        if subreddit in _SIMULATED_FAILURES:
            raise _SIMULATED_FAILURES[subreddit]()
        if subreddit == 'empty':
            return []
        now = self._clock.now()
        return [self._to_post(sample, subreddit, now) for sample in self._samples[:limit]]

    @staticmethod
    def _to_post(sample: SamplePost, subreddit: str, now) -> Post:
        slug = f'fx_{subreddit}_{sample.key}'
        return Post(
            id=f't3_{slug}',
            title=sample.title,
            author=sample.author,
            comment_count=sample.comment_count,
            score=sample.score,
            created_at=iso(now - timedelta(minutes=sample.minutes_ago)),
            permalink=f'https://www.reddit.com/r/{subreddit}/comments/{slug}/',
            subreddit=subreddit,
            preview_text=sample.preview_text,
            flair=sample.flair,
        )
