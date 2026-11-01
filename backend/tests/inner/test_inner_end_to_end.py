import asyncio
import json
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from app.composition import build_inner
from app.config import load_config
from app.errors import AppError
from tests.helpers import make_logger, make_post

BACKEND = Path(__file__).resolve().parents[2]


def ask(address, message):
    with socket.create_connection(address, timeout=10) as client:
        client.sendall((json.dumps(message) + '\n').encode())
        received = b''
        while data := client.recv(65536):
            received += data
    return json.loads(received)


def posts(term, freshness=None):
    args = {'term': term} if freshness is None else {'term': term, 'freshness': freshness}
    return {'v': 1, 'command': 'GET', 'resource': 'posts', 'args': args}


@pytest.fixture
def start(tmp_path):
    apps = []

    def start(collector=None, **env):
        config = load_config(
            {
                'COLLECTOR_MODE': 'fixture',
                'DB_PATH': str(tmp_path / 'x.db'),
                'INNER_PORT': '0',
                **env,
            }
        )
        app = build_inner(config, logger=make_logger(), collector=collector)
        threading.Thread(target=app.server.serve_forever, daemon=True).start()
        apps.append(app)
        return app.server.address

    yield start
    for app in apps:
        app.close()


def test_health_over_the_wire(start):
    reply = ask(start(), {'v': 1, 'command': 'GET', 'resource': 'health'})
    assert reply['ok'] is True
    assert reply['result']['collectorMode'] == 'fixture'


def test_auto_then_cached_then_live(start):
    address = start()
    replies = [ask(address, posts('r/Ubisoft')), ask(address, posts('ubisoft'))]
    replies.append(ask(address, posts('ubisoft', 'live')))
    sources = [reply['result']['collection']['source'] for reply in replies]
    assert sources == ['live', 'cache', 'live']
    ids = [[post['id'] for post in reply['result']['posts']] for reply in replies]
    assert ids[0] == ids[1] == ids[2] and len(ids[0]) == 7


def test_stored_after_a_collection_returns_it(start):
    address = start()
    collected = ask(address, posts('ubisoft'))['result']
    stored = ask(address, posts('ubisoft', 'stored'))['result']
    assert stored['posts'] == collected['posts']


@pytest.mark.parametrize(
    ('term', 'code', 'retryable'),
    [
        ('notfound', 'NOT_FOUND_SUBREDDIT', False),
        ('ratelimited', 'RATE_LIMITED', True),
        ('broken', 'UPSTREAM_ERROR', True),
        ('timeout', 'UPSTREAM_TIMEOUT', True),
    ],
)
def test_fixture_failures_map_to_error_replies(start, term, code, retryable):
    reply = ask(start(), posts(term))
    assert reply['ok'] is False
    assert (reply['error']['code'], reply['error']['retryable']) == (code, retryable)
    if code == 'RATE_LIMITED':
        assert reply['error']['retryAfterSeconds'] == 30


class SwitchableCollector:
    """Returns posts until `result` is set to an error; gated by a thread-safe event."""

    def __init__(self):
        self.calls = []
        self.result = [make_post('t3_a'), make_post('t3_b')]
        self.gate = threading.Event()
        self.gate.set()

    async def collect(self, subreddit, limit):
        self.calls.append(subreddit)
        await asyncio.to_thread(self.gate.wait, 10)
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result


def test_a_failure_after_a_success_carries_last_good(start):
    collector = SwitchableCollector()
    address = start(collector)
    ask(address, posts('ubisoft'))
    collector.result = AppError('UPSTREAM_ERROR')
    reply = ask(address, posts('ubisoft', 'live'))
    assert reply['error']['code'] == 'UPSTREAM_ERROR'
    assert reply['lastGood']['collection']['term'] == 'ubisoft'


def test_two_concurrent_auto_requests_share_one_collection(start):
    collector = SwitchableCollector()
    collector.gate.clear()
    address = start(collector)
    replies = []
    clients = [threading.Thread(target=lambda: replies.append(ask(address, posts('ubisoft'))))]
    clients[0].start()
    while not collector.calls:
        time.sleep(0.01)
    clients.append(threading.Thread(target=lambda: replies.append(ask(address, posts('ubisoft')))))
    clients[1].start()
    time.sleep(0.3)
    collector.gate.set()
    for client in clients:
        client.join(10)
    assert len(collector.calls) == 1
    assert len({reply['result']['collection']['id'] for reply in replies}) == 1


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def run_inner(tmp_path, **env):
    return subprocess.Popen(
        [sys.executable, '-m', 'app.inner'],
        cwd=BACKEND,
        env={**os.environ, 'COLLECTOR_MODE': 'fixture', 'DB_PATH': str(tmp_path / 's.db'), **env},
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def test_python_m_app_inner_serves_and_refuses_bad_config(tmp_path):
    port = free_port()
    process = run_inner(tmp_path, INNER_PORT=str(port), LOG_LEVEL='warning')
    try:
        for _ in range(50):
            try:
                reply = ask(('127.0.0.1', port), {'v': 1, 'command': 'GET', 'resource': 'health'})
                break
            except OSError:
                time.sleep(0.1)
        else:
            pytest.fail('inner server did not start')
        assert reply['result']['collectorMode'] == 'fixture'
    finally:
        process.terminate()
        process.wait(timeout=10)
    assert process.returncode == 0

    refused = run_inner(tmp_path, SERVER='nope')
    output, _ = refused.communicate(timeout=20)
    assert refused.returncode == 1
    assert 'Invalid configuration: SERVER' in output


def test_a_taken_port_is_a_clear_message_not_a_traceback(tmp_path):
    with socket.socket() as taken:
        taken.bind(('127.0.0.1', 0))
        taken.listen()
        port = taken.getsockname()[1]
        process = run_inner(tmp_path, INNER_PORT=str(port))
        output, _ = process.communicate(timeout=20)
    assert process.returncode == 1
    assert f'127.0.0.1:{port}' in output
    assert 'in use' in output
    assert 'Traceback' not in output


def test_importing_the_entry_module_does_not_start_a_server():
    result = subprocess.run(
        [sys.executable, '-c', 'import app.inner.__main__'],
        cwd=BACKEND,
        env={**os.environ, 'INNER_PORT': 'not-a-port'},
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert (result.returncode, result.stderr) == (0, '')


def test_the_feed_survives_a_restart_on_the_same_file(tmp_path):
    config = load_config(
        {'COLLECTOR_MODE': 'fixture', 'DB_PATH': str(tmp_path / 'r.db'), 'INNER_PORT': '0'}
    )
    replies = []
    for freshness in (None, 'stored'):
        app = build_inner(config, logger=make_logger())
        threading.Thread(target=app.server.serve_forever, daemon=True).start()
        try:
            replies.append(ask(app.server.address, posts('ubisoft', freshness))['result'])
        finally:
            app.close()
    assert replies[1]['posts'] == replies[0]['posts']


def test_re_collecting_never_duplicates_posts(start, tmp_path):
    import sqlite3

    address = start()
    ask(address, posts('ubisoft', 'live'))
    ask(address, posts('ubisoft', 'live'))
    with sqlite3.connect(tmp_path / 'x.db') as db:
        assert db.execute('SELECT COUNT(*) FROM posts').fetchone()[0] == 7


def test_relative_db_paths_resolve_from_the_repo_root(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config = load_config(
        {'COLLECTOR_MODE': 'fixture', 'DB_PATH': 'data/rel-test.db', 'INNER_PORT': '0'}
    )
    build_inner(config, logger=make_logger()).close()
    created = BACKEND.parent / 'data' / 'rel-test.db'
    try:
        assert created.exists()
        assert not (tmp_path / 'data').exists()
    finally:
        for suffix in ('', '-wal', '-shm'):
            Path(f'{created}{suffix}').unlink(missing_ok=True)
