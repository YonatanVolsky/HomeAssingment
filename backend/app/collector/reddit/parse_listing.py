"""Turn Reddit's mobile GraphQL `SubredditFeedElements` response into a list of Post.

Response shape (see docs/reddit-mobile-request.md):
    data.postFeed.prefixedName                       -> "r/ubisoft"
    data.postFeed.elements.edges[].node              -> one feed item
        __typename == "SubredditPost"                 (ads are "AdPost", skipped)
        id, createdAt, title, permalink, score, commentCount, isStickied
        authorInfo.name                               -> author
        content.markdown                              -> preview text (null for link posts)
        flair.text                                    -> flair
Only the envelope and the fields we read are validated; everything else is ignored, so new
fields Reddit adds do not break parsing.
"""

from typing import Any

from app.collector.mappers import (
    map_author,
    map_flair,
    to_absolute_permalink,
    to_iso_utc,
    truncate_preview,
)
from app.contracts import Post
from app.errors import AppError

_POST_TYPE = 'SubredditPost'


def _contract_error(reason: str) -> AppError:
    return AppError('CONTRACT_ERROR', cause=ValueError(reason))


def _require(body: dict[str, Any]) -> tuple[list[dict[str, Any]], str | None]:
    """Returns (edges, subreddit name) or raises CONTRACT_ERROR on an unexpected envelope."""
    data = body.get('data') if isinstance(body, dict) else None
    feed = data.get('postFeed') if isinstance(data, dict) else None
    if not isinstance(feed, dict):
        raise _contract_error('missing data.postFeed')
    elements = feed.get('elements')
    if not isinstance(elements, dict) or not isinstance(elements.get('edges'), list):
        raise _contract_error('missing postFeed.elements.edges')
    prefixed = feed.get('prefixedName')
    subreddit = prefixed[2:] if isinstance(prefixed, str) and prefixed.startswith('r/') else None
    return elements['edges'], subreddit


def parse_listing(body: dict[str, Any], limit: int) -> list[Post]:
    edges, subreddit = _require(body)

    posts: list[Post] = []
    seen: set[str] = set()
    post_nodes = 0
    for edge in edges:
        node = edge.get('node') if isinstance(edge, dict) else None
        if not isinstance(node, dict) or node.get('__typename') != _POST_TYPE:
            continue  # ad or unknown feed element
        post_nodes += 1
        post = _map_node(node, subreddit)
        if post is None or post.id in seen:
            continue
        seen.add(post.id)
        posts.append(post)
        if len(posts) >= limit:
            break

    if post_nodes > 0 and not posts:
        # Every real post failed to map: a schema change, not an empty subreddit.
        raise _contract_error('no post node could be mapped')
    return posts


def _map_node(node: dict[str, Any], subreddit: str | None) -> Post | None:
    """Maps one SubredditPost node, or None if a required field is missing or invalid."""
    reddit_id = node.get('id')
    title = node.get('title')
    if not isinstance(reddit_id, str) or not isinstance(title, str) or not title:
        return None
    try:
        created_at = to_iso_utc(node.get('createdAt'))
        permalink = to_absolute_permalink(node.get('permalink'))
    except AppError:
        return None  # a single bad node is skipped, not fatal

    content = node.get('content')
    markdown = content.get('markdown') if isinstance(content, dict) else None
    flair = node.get('flair')
    flair_text = flair.get('text') if isinstance(flair, dict) else None
    author = node.get('authorInfo')
    author_name = author.get('name') if isinstance(author, dict) else None

    return Post(
        id=reddit_id,
        title=title,
        author=map_author(author_name),
        comment_count=_non_negative_int(node.get('commentCount')),
        score=_int(node.get('score')),
        created_at=created_at,
        permalink=permalink,
        subreddit=subreddit,
        preview_text=truncate_preview(markdown),
        flair=map_flair(flair_text),
    )


def _int(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _non_negative_int(value: Any) -> int:
    return max(0, _int(value))
