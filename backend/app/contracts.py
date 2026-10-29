"""The JSON shapes exchanged with the frontend. Serialized with camelCase keys."""

from typing import Literal

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

CollectionSource = Literal['live', 'cache']


class ApiModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, frozen=True)


class Post(ApiModel):
    id: str
    """Reddit fullname, e.g. t3_abc123. Stable identity."""
    title: str
    author: str | None
    """None for deleted or anonymous authors."""
    comment_count: int
    score: int
    created_at: str
    """ISO 8601 UTC."""
    permalink: str
    """Absolute https://www.reddit.com/... URL."""
    subreddit: str | None
    preview_text: str | None
    """Plain text, at most 300 characters."""
    flair: str | None


class CollectionSummary(ApiModel):
    """Always a successful run."""

    id: int
    term: str
    source: CollectionSource
    """'cache' means served from the database without calling Reddit."""
    collected_at: str
    post_count: int


class CollectionResponse(ApiModel):
    collection: CollectionSummary | None
    """None only from GET /api/posts when the term was never collected."""
    posts: list[Post]
    """Newest first."""
