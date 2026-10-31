"""Commands and the dispatcher that hands each one to its resource's handler."""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Protocol

from app.errors import AppError


@dataclass(frozen=True)
class Command:
    """A CRUD verb on a resource, with its (already normalized) arguments."""

    verb: str
    resource: str
    args: Mapping[str, Any]


class CommandHandler(Protocol):
    def handle(self, command: Command) -> Any: ...


class Dispatcher:
    """Finds the handler for a command's resource and calls it."""

    def __init__(self, handlers: Mapping[str, CommandHandler]) -> None:
        self._handlers = MappingProxyType(dict(handlers))

    @property
    def resources(self) -> frozenset[str]:
        return frozenset(self._handlers)

    def handle(self, command: Command) -> Any:
        handler = self._handlers.get(command.resource)
        if handler is None:
            raise AppError('INVALID_REQUEST')
        return handler.handle(command)
