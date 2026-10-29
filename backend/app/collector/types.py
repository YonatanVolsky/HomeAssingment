from typing import Protocol

from app.contracts import Post


class Collector(Protocol):
    """Turns a normalized subreddit name into posts, or raises an AppError."""

    async def collect(self, subreddit: str, limit: int) -> list[Post]: ...
