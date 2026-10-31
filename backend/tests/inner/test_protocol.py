import json

import pytest

from app.errors import AppError, to_error_body
from app.inner.protocol import RawRequest, encode_error, encode_result, parse_request


def test_parses_a_valid_request():
    line = b'{"v":1,"command":"GET","resource":"posts","args":{"term":"x"}}\n'
    assert parse_request(line) == RawRequest(1, 'GET', 'posts', {'term': 'x'})


def test_missing_args_is_an_empty_dict():
    assert parse_request(b'{"v":1,"command":"GET","resource":"health"}\n').args == {}


VALID = {'v': 1, 'command': 'GET', 'resource': 'posts'}


def line(**changes):
    body = {**VALID, **changes}
    return (json.dumps({k: v for k, v in body.items() if v is not ...}) + '\n').encode()


@pytest.mark.parametrize(
    'raw',
    [
        b'\xff\n',
        b'not json\n',
        b'[]\n',
        b'null\n',
        b'"x"\n',
        line(v=2),
        line(v='1'),
        line(v=True),
        line(command=...),
        line(command=''),
        line(resource=5),
        line(args=[]),
    ],
)
def test_rejects_invalid_requests(raw):
    with pytest.raises(AppError) as raised:
        parse_request(raw)
    assert raised.value.code == 'INVALID_REQUEST'


def test_encode_result_is_one_compact_line():
    assert encode_result({'a': 'é'}) == '{"ok":true,"result":{"a":"é"}}\n'.encode()


def test_encode_error_carries_the_error_body_and_last_good():
    error = AppError('RATE_LIMITED', retry_after_seconds=30)
    decoded = json.loads(encode_error(error, {'x': 1}))
    assert decoded == {'ok': False, 'error': to_error_body(error), 'lastGood': {'x': 1}}
    assert 'lastGood' not in json.loads(encode_error(error))
    assert encode_error(error).endswith(b'\n')


def test_invalid_request_policy():
    error = AppError('INVALID_REQUEST')
    assert error.message == 'The request is not valid.'
    assert error.retryable is False
    assert error.auto_retry is False
