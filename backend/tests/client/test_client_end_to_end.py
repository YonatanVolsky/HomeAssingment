import os
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from app.composition import build_inner
from app.config import load_config
from tests.helpers import make_logger

BACKEND = Path(__file__).resolve().parents[2]


@pytest.fixture
def collector(tmp_path):
    config = load_config(
        {'COLLECTOR_MODE': 'fixture', 'DB_PATH': str(tmp_path / 'c.db'), 'INNER_PORT': '0'}
    )
    app = build_inner(config, logger=make_logger())
    threading.Thread(target=app.server.serve_forever, daemon=True).start()
    yield app.server.address
    app.close()


def client(typed, *args, **env):
    return subprocess.run(
        [sys.executable, '-m', 'app.client', *args],
        cwd=BACKEND,
        input=typed,
        env={**os.environ, **env},
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_a_session_against_the_real_collector(collector):
    _, port = collector
    typed = 'r/Ubisoft\n:stored ubisoft\nnotfound\n:json\n:health\n:quit\n'
    result = client(typed, '--port', str(port))

    assert result.returncode == 0, result.stderr
    out = result.stdout
    assert f'Connected to the collector at 127.0.0.1:{port} (fixture mode).' in out
    assert 'r/ubisoft · 7 posts · live' in out
    assert "'permalink': 'https://www.reddit.com/r/ubisoft/comments/" in out  # piped: not cut
    assert 'r/ubisoft · 7 posts · cache' in out
    assert 'error NOT_FOUND_SUBREDDIT' in out
    assert '"collectorMode": "fixture"' in out


def test_the_address_comes_from_the_environment(collector):
    _, port = collector
    result = client(':quit\n', INNER_PORT=str(port))
    assert f'127.0.0.1:{port} (fixture mode)' in result.stdout


def test_a_bad_port_is_a_usage_error_not_a_traceback():
    result = client('', INNER_PORT='abc')
    assert result.returncode == 2
    assert 'Traceback' not in result.stderr
    assert '--port' in result.stderr
