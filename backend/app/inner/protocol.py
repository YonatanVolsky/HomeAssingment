"""The inner server's wire format: one UTF-8 JSON object per line, one request per connection.

The only module that knows the format; see docs/inner-protocol.md.
    request:  {"v": 1, "command": "GET", "resource": "posts", "args": {...}}
    success:  {"ok": true, "result": ...}
    failure:  {"ok": false, "error": {code, message, retryable, retryAfterSeconds?},
               "lastGood"?: ...}
"""

import json
from dataclasses import dataclass
from typing import Any

from app.errors import AppError, to_error_body

PROTOCOL_VERSION = 1
MAX_LINE_BYTES = 4096


@dataclass(frozen=True)
class RawRequest:
    version: int
    command: str
    resource: str
    args: dict[str, Any]


def parse_request(line: bytes) -> RawRequest:
    """Parses one request line, or raises INVALID_REQUEST."""
    try:
        message = json.loads(line.decode('utf-8'))
    except (UnicodeDecodeError, ValueError) as cause:
        raise AppError('INVALID_REQUEST', cause=cause) from cause
    if not isinstance(message, dict):
        raise AppError('INVALID_REQUEST')
    version = message.get('v')
    command = message.get('command')
    resource = message.get('resource')
    args = message.get('args', {})
    # `type(...) is int` because True is an int too.
    if type(version) is not int or version != PROTOCOL_VERSION:
        raise AppError('INVALID_REQUEST')
    if not _non_empty_str(command) or not _non_empty_str(resource) or not isinstance(args, dict):
        raise AppError('INVALID_REQUEST')
    return RawRequest(version, command, resource, args)


def encode_result(result: Any) -> bytes:
    return _line({'ok': True, 'result': result})


def encode_error(error: AppError, last_good: Any | None = None) -> bytes:
    reply: dict[str, Any] = {'ok': False, 'error': to_error_body(error)}
    if last_good is not None:
        reply['lastGood'] = last_good
    return _line(reply)


def _non_empty_str(value: object) -> bool:
    return isinstance(value, str) and value != ''


def _line(message: dict[str, Any]) -> bytes:
    return (json.dumps(message, ensure_ascii=False, separators=(',', ':')) + '\n').encode()
