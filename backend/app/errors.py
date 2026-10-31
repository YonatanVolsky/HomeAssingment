"""One table decides HTTP status, collector auto-retry and UI retryability for every error."""

from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal, TypedDict

ErrorCode = Literal[
    'INVALID_TERM',
    'INVALID_REQUEST',
    'RATE_LIMITED',
    'UPSTREAM_AUTH',
    'UPSTREAM_ERROR',
    'UPSTREAM_TIMEOUT',
    'NOT_FOUND_SUBREDDIT',
    'CONTRACT_ERROR',
    'DB_ERROR',
    'INTERNAL',
]


@dataclass(frozen=True)
class ErrorPolicy:
    http_status: int
    auto_retry: bool
    """Whether the collector re-sends the same request itself before giving up."""
    retryable: bool
    """Whether the UI offers "Try again" without the user changing the input."""
    default_message: str


ERROR_TABLE: MappingProxyType[str, ErrorPolicy] = MappingProxyType(
    {
        'INVALID_TERM': ErrorPolicy(400, False, False, 'Enter a subreddit name like r/ubisoft.'),
        'INVALID_REQUEST': ErrorPolicy(400, False, False, 'The request is not valid.'),
        'RATE_LIMITED': ErrorPolicy(
            429, False, True, 'Reddit is limiting requests. Try again shortly.'
        ),
        'UPSTREAM_AUTH': ErrorPolicy(502, False, True, 'Could not authenticate with Reddit.'),
        'UPSTREAM_ERROR': ErrorPolicy(502, True, True, 'Reddit is unavailable right now.'),
        'UPSTREAM_TIMEOUT': ErrorPolicy(504, True, True, 'Reddit took too long to respond.'),
        'NOT_FOUND_SUBREDDIT': ErrorPolicy(
            404, False, False, 'That subreddit was not found or is not public.'
        ),
        'CONTRACT_ERROR': ErrorPolicy(502, False, True, 'Reddit returned an unexpected response.'),
        'DB_ERROR': ErrorPolicy(500, False, True, 'Could not save results locally.'),
        'INTERNAL': ErrorPolicy(500, False, True, 'Something went wrong.'),
    }
)


class ErrorBody(TypedDict, total=False):
    code: ErrorCode
    message: str
    retryable: bool
    retryAfterSeconds: int


class AppError(Exception):
    """An error whose message is safe to show users. The cause is for logs only."""

    def __init__(
        self,
        code: ErrorCode,
        message: str | None = None,
        *,
        cause: BaseException | None = None,
        retry_after_seconds: int | None = None,
        auto_retry: Literal[False] | None = None,
        retryable: Literal[False] | None = None,
    ) -> None:
        self.code: ErrorCode = code
        self.retry_after_seconds = retry_after_seconds
        self.message = message or _default_message(code, retry_after_seconds)
        # Only False is meaningful: it switches off what the table would allow.
        self._auto_retry_override = auto_retry
        self._retryable_override = retryable
        super().__init__(self.message)
        self.__cause__ = cause

    @property
    def http_status(self) -> int:
        return ERROR_TABLE[self.code].http_status

    @property
    def retryable(self) -> bool:
        if self._retryable_override is not None:
            return self._retryable_override
        return ERROR_TABLE[self.code].retryable

    @property
    def auto_retry(self) -> bool:
        if self._auto_retry_override is not None:
            return self._auto_retry_override
        return ERROR_TABLE[self.code].auto_retry


def _default_message(code: ErrorCode, retry_after_seconds: int | None) -> str:
    if code == 'RATE_LIMITED' and retry_after_seconds is not None:
        return f'Reddit is limiting requests. Try again in {retry_after_seconds} seconds.'
    return ERROR_TABLE[code].default_message


def to_error_body(error: AppError) -> ErrorBody:
    body: ErrorBody = {'code': error.code, 'message': error.message, 'retryable': error.retryable}
    if error.retry_after_seconds is not None:
        body['retryAfterSeconds'] = error.retry_after_seconds
    return body
