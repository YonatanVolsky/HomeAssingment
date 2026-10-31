import pytest

from app.errors import AppError
from app.inner.dispatcher import Command, Dispatcher
from app.inner.handlers import ResourceHandler


class RecordingHandler:
    def __init__(self):
        self.commands = []

    def handle(self, command):
        self.commands.append(command)
        return {'handled': command.resource}


def assert_invalid_request(call, *args):
    with pytest.raises(AppError) as raised:
        call(*args)
    assert raised.value.code == 'INVALID_REQUEST'


def test_dispatches_to_the_resources_handler():
    posts = RecordingHandler()
    command = Command('GET', 'posts', {})
    assert Dispatcher({'posts': posts}).handle(command) == {'handled': 'posts'}
    assert posts.commands == [command]


def test_unknown_resource_is_invalid_request():
    dispatcher = Dispatcher({'posts': RecordingHandler()})
    assert_invalid_request(dispatcher.handle, Command('GET', 'x', {}))


def test_resources_lists_the_handler_names():
    dispatcher = Dispatcher({'posts': RecordingHandler(), 'health': RecordingHandler()})
    assert dispatcher.resources == frozenset({'posts', 'health'})


class GetOnly(ResourceHandler):
    def get(self, args):
        return args['x']


def test_resource_handler_calls_the_verb_method():
    assert GetOnly().handle(Command('GET', 'r', {'x': 1})) == 1


@pytest.mark.parametrize('verb', ['POST', 'PUT', 'DELETE', 'PATCH', '__init__'])
def test_unsupported_verbs_are_invalid_request(verb):
    assert_invalid_request(GetOnly().handle, Command(verb, 'r', {}))
