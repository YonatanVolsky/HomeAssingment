import pytest

from app.errors import ERROR_TABLE, AppError, to_error_body


def test_derives_http_status_and_retryable_from_the_code():
    error = AppError('NOT_FOUND_SUBREDDIT', 'r/x was not found')

    assert error.http_status == 404
    assert error.retryable is False
    assert error.message == 'r/x was not found'


def test_falls_back_to_the_default_message_of_the_code():
    assert AppError('UPSTREAM_TIMEOUT').message == 'Reddit took too long to respond.'


def test_rate_limit_message_includes_the_wait():
    error = AppError('RATE_LIMITED', retry_after_seconds=12)
    assert error.retry_after_seconds == 12
    assert '12 seconds' in error.message


@pytest.mark.parametrize(
    ('code', 'http', 'auto_retry', 'retryable'),
    [
        ('INVALID_TERM', 400, False, False),
        ('RATE_LIMITED', 429, False, True),
        ('UPSTREAM_AUTH', 502, False, True),
        ('UPSTREAM_ERROR', 502, True, True),
        ('UPSTREAM_TIMEOUT', 504, True, True),
        ('NOT_FOUND_SUBREDDIT', 404, False, False),
        ('CONTRACT_ERROR', 502, False, True),
        ('DB_ERROR', 500, False, True),
        ('INTERNAL', 500, False, True),
    ],
)
def test_error_table(code, http, auto_retry, retryable):
    policy = ERROR_TABLE[code]
    actual = (policy.http_status, policy.auto_retry, policy.retryable)
    assert actual == (http, auto_retry, retryable)


def test_table_covers_ten_codes():
    assert len(ERROR_TABLE) == 10


def test_auto_retry_follows_the_table_unless_switched_off():
    assert AppError('UPSTREAM_ERROR').auto_retry is True
    turned_off = AppError('UPSTREAM_ERROR', auto_retry=False)
    assert turned_off.auto_retry is False
    assert turned_off.retryable is True


def test_retryable_can_be_switched_off_for_one_error():
    error = AppError('UPSTREAM_ERROR', retryable=False)
    assert error.retryable is False
    assert to_error_body(error)['retryable'] is False


def test_error_body_never_includes_the_cause():
    cause = RuntimeError('Authorization: Bearer secret-token')
    error = AppError('UPSTREAM_AUTH', cause=cause)

    body = to_error_body(error)

    assert error.__cause__ is cause
    assert 'secret-token' not in str(body)
    assert body == {
        'code': 'UPSTREAM_AUTH',
        'message': 'Could not authenticate with Reddit.',
        'retryable': True,
    }


def test_error_body_includes_retry_after_only_when_present():
    assert to_error_body(AppError('RATE_LIMITED', retry_after_seconds=5))['retryAfterSeconds'] == 5
    assert 'retryAfterSeconds' not in to_error_body(AppError('INTERNAL'))
