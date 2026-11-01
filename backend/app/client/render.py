"""Formats a protocol reply for the prompt: readable text, or the raw JSON."""

import json
from datetime import datetime
from typing import Any

_POST_FIELDS = ('title', 'author', 'score', 'commentCount', 'permalink')


def render(resource: str, reply: dict[str, Any], *, as_json: bool, width: int | None = None) -> str:
    """`width`: cut each post line to this many characters, like the brief's example."""
    if as_json:
        return json.dumps(reply, indent=2, ensure_ascii=False)
    if not reply['ok']:
        return _error(reply, width)
    if resource == 'health':
        return _health(reply['result'])
    return _feed(reply['result'], width)


def _feed(result: dict[str, Any], width: int | None) -> str:
    collection = result['collection']
    if collection is None:
        return 'Nothing stored for this subreddit yet.'
    lines = [
        f'r/{collection["term"]} · {_count(collection["postCount"], "post")} · '
        f'{collection["source"]} · collected {_time(collection["collectedAt"])}'
    ]
    # One line per post, like the brief's example output: `00: {'title': ..., ...}`.
    digits = max(2, len(str(len(result['posts']) - 1)))
    for number, post in enumerate(result['posts']):
        fields = {key: post[key] for key in _POST_FIELDS}
        lines.append(_fit(f'{number:0{digits}d}: {fields!r}', width))
    if not result['posts']:
        lines.append('No posts found.')
    return '\n'.join(lines)


def _health(result: dict[str, Any]) -> str:
    return (
        f'status {result["status"]} · database {result["db"]} · '
        f'mode {result["collectorMode"]} · stale after {result["staleAfterSeconds"]} s'
    )


def _error(reply: dict[str, Any], width: int | None) -> str:
    error = reply['error']
    # A rate limit's wait is already in its message (retryAfterSeconds is in the JSON).
    hint = 'can retry' if error['retryable'] else 'no retry'
    text = f'error {error["code"]}: {error["message"]} ({hint})'
    if reply.get('lastGood'):
        text += '\nLast good feed:\n' + _feed(reply['lastGood'], width)
    return text


def _fit(line: str, width: int | None) -> str:
    if width is None or len(line) <= width:
        return line
    return line[: width - 1] + '…'


def _count(number: int, noun: str) -> str:
    return f'{number} {noun}' if number == 1 else f'{number} {noun}s'


def _time(iso: str) -> str:
    return datetime.fromisoformat(iso).strftime('%Y-%m-%d %H:%M:%S UTC')
