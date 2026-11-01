"""Turns one typed line into what the prompt should do. Knows the prompt's syntax only."""

from dataclasses import dataclass
from typing import Any

from app.inner.protocol import PROTOCOL_VERSION

FRESHNESS = ('auto', 'live', 'stored')
_QUIT = ('quit', 'exit', 'q')


@dataclass(frozen=True)
class Send:
    """A protocol message for the collector."""

    message: dict[str, Any]


@dataclass(frozen=True)
class ToggleJson:
    pass


@dataclass(frozen=True)
class Help:
    pass


@dataclass(frozen=True)
class Quit:
    pass


@dataclass(frozen=True)
class Invalid:
    reason: str


Command = Send | ToggleJson | Help | Quit | Invalid


def parse(line: str) -> Command | None:
    """None for a blank line. A plain term means `:auto <term>`."""
    text = line.strip()
    if not text:
        return None
    if not text.startswith(':'):
        return _posts(text, 'auto')
    name, _, rest = text[1:].partition(' ')
    name, rest = name.lower(), rest.strip()
    if name in FRESHNESS:
        return _posts(rest, name) if rest else Invalid(f':{name} needs a subreddit.')
    if rest:
        return Invalid(f':{name} takes no arguments. Type :help for commands.')
    if name == 'health':
        return health()
    if name == 'json':
        return ToggleJson()
    if name == 'help':
        return Help()
    if name in _QUIT:
        return Quit()
    return Invalid(f'Unknown command :{name}. Type :help for commands.')


def health() -> Send:
    return Send(_message('health'))


def _posts(term: str, freshness: str) -> Send:
    # Sent as typed: normalizing is the collector's job.
    return Send(_message('posts', {'term': term, 'freshness': freshness}))


def _message(resource: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
    message: dict[str, Any] = {'v': PROTOCOL_VERSION, 'command': 'GET', 'resource': resource}
    if args is not None:
        message['args'] = args
    return message
