"""Formats a protocol reply for the prompt: readable text, or the raw JSON."""

import json
from datetime import datetime
from typing import Any


def render(resource: str, reply: dict[str, Any], *, as_json: bool) -> str:
    if as_json:
        return json.dumps(reply, indent=2, ensure_ascii=False)
    if not reply['ok']:
        return _error(reply)
    if resource == 'health':
        return _health(reply['result'])
    return _feed(reply['result'])


def _feed(result: dict[str, Any]) -> str:
    collection = result['collection']
    if collection is None:
        return 'Nothing stored for this subreddit yet.'
    lines = [
        f'r/{collection["term"]} · {_count(collection["postCount"], "post")} · '
        f'{collection["source"]} · collected {_time(collection["collectedAt"])}'
    ]
    for number, post in enumerate(result['posts'], start=1):
        lines += [
            f'  {number}. {post["title"]}',
            f'     u/{post["author"] or "[deleted]"} · {_count(post["score"], "point")} · '
            f'{_count(post["commentCount"], "comment")}',
            f'     {post["permalink"]}',
        ]
    if not result['posts']:
        lines.append('  No posts found.')
    return '\n'.join(lines)


def _health(result: dict[str, Any]) -> str:
    return (
        f'status {result["status"]} · database {result["db"]} · '
        f'mode {result["collectorMode"]} · stale after {result["staleAfterSeconds"]} s'
    )


def _error(reply: dict[str, Any]) -> str:
    error = reply['error']
    # A rate limit's wait is already in its message (retryAfterSeconds is in the JSON).
    hint = 'can retry' if error['retryable'] else 'no retry'
    text = f'error {error["code"]}: {error["message"]} ({hint})'
    if reply.get('lastGood'):
        text += '\nLast good feed:\n' + _feed(reply['lastGood'])
    return text


def _count(number: int, noun: str) -> str:
    return f'{number} {noun}' if number == 1 else f'{number} {noun}s'


def _time(iso: str) -> str:
    return datetime.fromisoformat(iso).strftime('%Y-%m-%d %H:%M:%S UTC')
