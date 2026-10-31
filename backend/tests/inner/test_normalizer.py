import json
import logging

import pytest

from app.errors import AppError
from app.inner.dispatcher import Command
from app.inner.normalizer import RequestNormalizer
from tests.helpers import make_logger, make_normalizer


class RecordingNext:
    def __init__(self, result=None, error=None):
        self.commands = []
        self.result = {'done': True} if result is None else result
        self.error = error

    def handle(self, command):
        self.commands.append(command)
        if self.error is not None:
            raise self.error
        return self.result


def make(next_stage):
    return RequestNormalizer(make_normalizer(), next_stage, make_logger())


def send(stage, message):
    raw = message if isinstance(message, bytes) else (json.dumps(message) + '\n').encode()
    return json.loads(stage.handle(raw))


def posts(**args):
    return {'v': 1, 'command': 'get', 'resource': 'posts', 'args': args}


def test_normalizes_the_term_and_uppercases_the_verb():
    next_stage = RecordingNext()
    reply = send(make(next_stage), posts(term=' r/Ubisoft ', freshness='live'))
    assert next_stage.commands == [
        Command('GET', 'posts', {'term': 'ubisoft', 'freshness': 'live'})
    ]
    assert reply == {'ok': True, 'result': {'done': True}}


def test_requests_without_a_term_pass_through():
    next_stage = RecordingNext()
    send(make(next_stage), {'v': 1, 'command': 'GET', 'resource': 'health'})
    assert next_stage.commands == [Command('GET', 'health', {})]


@pytest.mark.parametrize('term', ['bad name!', 'a' * 201, 5])
def test_invalid_terms_are_an_error_reply_and_never_dispatched(term):
    next_stage = RecordingNext()
    reply = send(make(next_stage), posts(term=term))
    assert reply['ok'] is False
    assert reply['error']['code'] == 'INVALID_TERM'
    assert next_stage.commands == []


def test_an_invalid_line_is_an_invalid_request_reply():
    assert send(make(RecordingNext()), b'[]\n')['error']['code'] == 'INVALID_REQUEST'


class FailedWithHistory(AppError):
    def __init__(self, code):
        super().__init__(code)
        self.last_good = {'x': 1}


def test_last_good_on_an_error_is_written():
    reply = send(make(RecordingNext(error=FailedWithHistory('UPSTREAM_ERROR'))), posts(term='x1'))
    assert reply['error']['code'] == 'UPSTREAM_ERROR'
    assert reply['lastGood'] == {'x': 1}


def test_an_unexpected_exception_is_a_logged_internal_reply(caplog):
    stage = make(RecordingNext(error=RuntimeError('secret')))
    with caplog.at_level(logging.ERROR):
        raw = stage.handle((json.dumps(posts(term='x1')) + '\n').encode())
    assert json.loads(raw)['error']['code'] == 'INTERNAL'
    assert b'secret' not in raw
    assert any(record.exc_info for record in caplog.records)
