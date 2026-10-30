import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import httpx
import pytest

from app.collector.fixture_collector import DEFAULT_SAMPLE_FILE, FixtureCollector
from app.errors import AppError
from app.main import create_app_from_env

pytestmark = pytest.mark.anyio
BACKEND = Path(__file__).resolve().parents[1]


def fixture_env(tmp_path, **extra):
    return {'COLLECTOR_MODE': 'fixture', 'DB_PATH': str(tmp_path / 'test.db'), **extra}


async def call(app, method, url, **kwargs):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url='http://test') as client:
        return await client.request(method, url, **kwargs)


async def test_the_feed_survives_a_restart_on_the_same_file(tmp_path):
    app, close = create_app_from_env(fixture_env(tmp_path))
    collected = (await call(app, 'POST', '/api/collections', json={'term': 'ubisoft'})).json()
    close()

    app, close = create_app_from_env(fixture_env(tmp_path))
    read = (await call(app, 'GET', '/api/posts', params={'term': 'ubisoft'})).json()
    close()

    assert read['posts'] == collected['posts']
    assert read['collection']['id'] == collected['collection']['id']
    assert read['collection']['source'] == 'cache'


async def test_re_collecting_never_duplicates_posts(tmp_path):
    app, close = create_app_from_env(fixture_env(tmp_path))
    for _ in range(2):
        await call(app, 'POST', '/api/collections', json={'term': 'ubisoft', 'force': True})
    close()

    import sqlite3

    db = sqlite3.connect(tmp_path / 'test.db')
    posts, runs = db.execute(
        'SELECT (SELECT COUNT(*) FROM posts), (SELECT COUNT(*) FROM collections)'
    ).fetchone()
    db.close()
    assert (posts, runs) == (7, 2)


async def test_a_failure_after_a_success_keeps_the_last_good_feed(tmp_path, monkeypatch):
    app, close = create_app_from_env(fixture_env(tmp_path))
    await call(app, 'POST', '/api/collections', json={'term': 'ubisoft'})
    close()

    async def failing(self, subreddit, limit):
        raise AppError('UPSTREAM_TIMEOUT')

    monkeypatch.setattr(FixtureCollector, 'collect', failing)
    app, close = create_app_from_env(fixture_env(tmp_path))
    response = await call(app, 'POST', '/api/collections', json={'term': 'ubisoft', 'force': True})
    close()

    assert response.status_code == 504
    assert len(response.json()['lastGood']['posts']) == 7
    assert DEFAULT_SAMPLE_FILE.exists()


def test_relative_db_paths_resolve_from_the_repo_root(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _, close = create_app_from_env({'COLLECTOR_MODE': 'fixture', 'DB_PATH': 'data/rel-test.db'})
    close()
    created = BACKEND.parent / 'data' / 'rel-test.db'
    try:
        assert created.exists()
        assert not (tmp_path / 'data').exists()
    finally:
        for suffix in ('', '-wal', '-shm'):
            Path(f'{created}{suffix}').unlink(missing_ok=True)


def test_live_mode_starts_without_the_not_available_warning(tmp_path, capsys):
    _, close = create_app_from_env({'DB_PATH': str(tmp_path / 'live.db')})
    close()
    assert 'not available yet' not in capsys.readouterr().err


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def run_server(env):
    return subprocess.Popen(
        [sys.executable, '-m', 'app'],
        cwd=BACKEND,
        env={**os.environ, **env},
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def test_python_m_app_serves_the_api(tmp_path):
    port = free_port()
    server = run_server({**fixture_env(tmp_path), 'PORT': str(port), 'LOG_LEVEL': 'warning'})
    try:
        for _ in range(50):
            try:
                with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/health') as response:
                    body = json.loads(response.read())
                break
            except OSError:
                time.sleep(0.1)
        else:
            pytest.fail('server did not start')
        assert body['collectorMode'] == 'fixture'
    finally:
        server.terminate()
        server.wait(timeout=10)


def test_python_m_app_refuses_invalid_configuration(tmp_path):
    server = run_server({**fixture_env(tmp_path), 'PORT': 'abc'})
    output, _ = server.communicate(timeout=20)
    assert server.returncode == 1
    assert 'Invalid configuration: PORT' in output
