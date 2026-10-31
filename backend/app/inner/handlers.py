"""Resource handlers: one class per resource, one method per CRUD verb it supports."""

from collections.abc import Mapping
from typing import Any

from app.errors import AppError
from app.inner.dispatcher import Command

# A fixed table, so a verb from the wire can never name an arbitrary method.
_VERB_METHODS = {'GET': 'get', 'POST': 'post', 'PUT': 'put', 'DELETE': 'delete'}
_NOT_SUPPORTED = 'This command is not supported for this resource.'


class ResourceHandler:
    """Calls the method for the command's verb. A resource overrides only what it supports."""

    def handle(self, command: Command) -> Any:
        method = _VERB_METHODS.get(command.verb)
        if method is None:
            raise AppError('INVALID_REQUEST', _NOT_SUPPORTED)
        return getattr(self, method)(command.args)

    def get(self, args: Mapping[str, Any]) -> Any:
        raise AppError('INVALID_REQUEST', _NOT_SUPPORTED)

    def post(self, args: Mapping[str, Any]) -> Any:
        raise AppError('INVALID_REQUEST', _NOT_SUPPORTED)

    def put(self, args: Mapping[str, Any]) -> Any:
        raise AppError('INVALID_REQUEST', _NOT_SUPPORTED)

    def delete(self, args: Mapping[str, Any]) -> Any:
        raise AppError('INVALID_REQUEST', _NOT_SUPPORTED)
