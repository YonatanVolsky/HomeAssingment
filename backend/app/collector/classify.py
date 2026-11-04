import math
from collections.abc import Mapping

from curl_cffi.requests.exceptions import Timeout as CurlTimeout

from app.errors import AppError

DEFAULT_RETRY_AFTER_SECONDS = 30


def classify_status(status: int, headers: Mapping[str, str]) -> AppError | None:
    """Maps an HTTP status from Reddit to an AppError, or None for success."""
    if 200 <= status < 300:
        return None
    cause = RuntimeError(f'Reddit responded with HTTP {status}')
    if status in (401, 403):
        return AppError('UPSTREAM_AUTH', cause=cause)
    if status == 404:
        return AppError('NOT_FOUND_SUBREDDIT', cause=cause)
    if status == 429:
        return AppError('RATE_LIMITED', cause=cause, retry_after_seconds=_retry_after(headers))
    if status >= 500:
        return AppError('UPSTREAM_ERROR', cause=cause)
    return AppError('UPSTREAM_ERROR', cause=cause, auto_retry=False)


def classify_network_error(error: BaseException) -> AppError:
    """Maps a raised network or timeout error to an AppError. AppErrors pass through."""
    if isinstance(error, AppError):
        return error
    # curl_cffi's Timeout is an OSError, not a TimeoutError, so it is named here.
    is_timeout = isinstance(error, CurlTimeout | TimeoutError)
    return AppError('UPSTREAM_TIMEOUT' if is_timeout else 'UPSTREAM_ERROR', cause=error)


def _retry_after(headers: Mapping[str, str]) -> int:
    lowered = {key.lower(): value for key, value in headers.items()}
    for name in ('retry-after', 'x-ratelimit-reset'):
        try:
            value = float(lowered[name])
        except (KeyError, ValueError):
            continue
        if math.isfinite(value) and value > 0:
            return math.ceil(value)
    return DEFAULT_RETRY_AFTER_SECONDS
