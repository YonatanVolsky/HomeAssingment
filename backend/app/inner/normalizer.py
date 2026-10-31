"""First stage of the inner server's chain: request line in, reply line out.

Parses and validates the message, normalizes the term with the configured term protocol,
and hands a Command to the next stage. Every failure becomes an error reply, so the server
never has to know about errors.
"""

import logging
from typing import Any

from app.errors import AppError
from app.inner.dispatcher import Command, CommandHandler
from app.inner.protocol import encode_error, encode_result, parse_request
from app.terms.normalizer import Normalizer

MAX_TERM_LENGTH = 200


class RequestNormalizer:
    def __init__(
        self, term_normalizer: Normalizer, next: CommandHandler, logger: logging.Logger
    ) -> None:
        self._term_normalizer = term_normalizer
        self._next = next
        self._logger = logger

    def handle(self, line: bytes) -> bytes:
        try:
            return encode_result(self._next.handle(self._to_command(line)))
        except AppError as error:
            return encode_error(error, getattr(error, 'last_good', None))
        except Exception as error:
            self._logger.error('unexpected error while handling a request', exc_info=error)
            return encode_error(AppError('INTERNAL', cause=error))

    def _to_command(self, line: bytes) -> Command:
        request = parse_request(line)
        args = dict(request.args)
        if 'term' in args:
            args['term'] = self._normalize_term(args['term'])
        return Command(request.command.upper(), request.resource, args)

    def _normalize_term(self, term: Any) -> str:
        if not isinstance(term, str) or len(term) > MAX_TERM_LENGTH:
            raise AppError('INVALID_TERM')
        return self._term_normalizer.normalize(term)
