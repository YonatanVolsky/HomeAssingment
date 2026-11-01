import json

import pytest

from app.client.connection import ConnectionFailed
from app.client.repl import Repl
from tests.helpers import make_post

HEALTH = {
    'ok': True,
    'result': {'status': 'ok', 'db': 'ok', 'collectorMode': 'fixture', 'staleAfterSeconds': 600},
}
EMPTY = {'ok': True, 'result': {'collection': None, 'posts': []}}


class FakeConnection:
    host, port = '127.0.0.1', 3002

    def __init__(self, *replies):
        self.replies = list(replies)
        self.sent = []

    def send(self, message):
        self.sent.append(message)
        reply = self.replies.pop(0)
        if isinstance(reply, BaseException):
            raise reply
        return reply


def session(connection, *lines, end=EOFError):
    """Runs the prompt over `lines`, then `end` (Ctrl+D by default); returns all output."""
    remaining = list(lines)
    output = []

    def read(prompt):
        output.append(prompt)
        if not remaining:
            raise end()
        return remaining.pop(0)

    Repl(connection, read, output.append).run()
    return '\n'.join(output)


def test_starts_with_the_collector_address_and_mode():
    out = session(FakeConnection(HEALTH))
    assert 'Connected to the collector at 127.0.0.1:3002 (fixture mode).' in out
    assert ':help' in out


def test_starts_even_when_the_collector_is_down():
    down = ConnectionFailed('collector not reachable at 127.0.0.1:3002')
    connection = FakeConnection(down, EMPTY)
    out = session(connection, 'ubisoft')
    assert 'collector not reachable at 127.0.0.1:3002' in out
    assert 'npm run dev:inner' in out
    assert len(connection.sent) == 2  # it kept prompting and sent the next command


def test_a_term_is_sent_and_its_reply_rendered():
    connection = FakeConnection(HEALTH, EMPTY)
    out = session(connection, 'r/ubisoft')
    assert connection.sent[1]['args'] == {'term': 'r/ubisoft', 'freshness': 'auto'}
    assert 'Nothing stored for this subreddit yet.' in out


def test_json_toggles_raw_output():
    out = session(FakeConnection(HEALTH, EMPTY, EMPTY), ':json', 'a', ':json', 'b')
    assert 'JSON output on.' in out and 'JSON output off.' in out
    assert out.count('Nothing stored for this subreddit yet.') == 1
    assert json.dumps(EMPTY, indent=2) in out


def test_a_failed_send_is_reported_and_the_prompt_continues():
    connection = FakeConnection(HEALTH, ConnectionFailed('no reply within 35 s'), EMPTY)
    out = session(connection, 'a', 'b')
    assert 'no reply within 35 s' in out
    assert len(connection.sent) == 3


def test_invalid_input_and_help_are_answered_locally():
    connection = FakeConnection(HEALTH)
    out = session(connection, ':nope', ':help')
    assert 'Unknown command :nope' in out
    assert ':live <subreddit>' in out
    assert len(connection.sent) == 1


@pytest.mark.parametrize('end', [EOFError, KeyboardInterrupt])
def test_ctrl_d_or_ctrl_c_at_the_prompt_quits(end):
    connection = FakeConnection(HEALTH)
    session(connection, end=end)
    assert len(connection.sent) == 1


def test_quit_stops_reading():
    connection = FakeConnection(HEALTH)
    session(connection, ':quit', 'never sent')
    assert len(connection.sent) == 1


def test_ctrl_c_while_waiting_cancels_that_request_only():
    connection = FakeConnection(HEALTH, KeyboardInterrupt(), EMPTY)
    out = session(connection, 'slow', 'next')
    assert 'Cancelled.' in out
    assert len(connection.sent) == 3


def test_post_lines_are_cut_at_the_current_terminal_width():
    reply = {
        'ok': True,
        'result': {
            'collection': {
                'id': 1,
                'term': 'ubisoft',
                'source': 'live',
                'collectedAt': '2026-10-31T14:55:24.992Z',
                'postCount': 1,
            },
            'posts': [make_post('t3_a', title='z' * 200).model_dump(by_alias=True)],
        },
    }
    output = []
    lines = iter(['ubisoft'])

    def read(_prompt):
        try:
            return next(lines)
        except StopIteration:
            raise EOFError from None

    Repl(FakeConnection(HEALTH, reply), read, output.append, width=lambda: 50).run()
    post_line = next(
        line for chunk in output for line in chunk.splitlines() if line.startswith('00:')
    )
    assert len(post_line) == 50 and post_line.endswith('…')
