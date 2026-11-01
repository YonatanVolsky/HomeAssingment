import pytest

from app.errors import ERROR_TABLE, AppError, to_error_body


def test_derives_retryable_from_the_code():
    error = AppError('NOT_FOUND_SUBREDDIT', 'r/x was not found')

    assert error.retryable is False
    assert error.message == 'r/x was not found'


def test_falls_back_to_the_default_message_of_the_code():
    assert AppError('UPSTREAM_TIMEOUT').message == 'Reddit took too long to respond.'


def test_rate_limit_message_includes_the_wait():
    error = AppError('RATE_LIMITED', retry_after_seconds=12)
    assert error.retry_after_seconds == 12
    assert '12 seconds' in error.message


@pytest.mark.parametrize(
    ('code', 'auto_retry', 'retryable'),
    [
        ('INVALID_TERM', False, False),
        ('RATE_LIMITED', False, True),
        ('UPSTREAM_AUTH', False, True),
        ('UPSTREAM_ERROR', True, True),
        ('UPSTREAM_TIMEOUT', True, True),
        ('NOT_FOUND_SUBREDDIT', False, False),
        ('CONTRACT_ERROR', False, True),
        ('DB_ERROR', False, True),
        ('INTERNAL', False, True),
        ('BUSY', False, True),
    ],
)
def test_error_table(code, auto_retry, retryable):
    policy = ERROR_TABLE[code]
    assert (policy.auto_retry, policy.retryable) == (auto_retry, retryable)


def test_http_status_is_not_known_here():
    assert not hasattr(AppError('INTERNAL'), 'http_status')


def test_table_covers_eleven_codes():
    assert len(ERROR_TABLE) == 11


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
