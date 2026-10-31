import dataclasses

import pytest

from app.config import ConfigError, load_config


def test_applies_defaults_when_the_environment_is_empty():
    config = load_config({})

    assert config.port == 3001
    assert config.host == '127.0.0.1'
    assert config.collector_mode == 'live'
    assert config.db_path == './data/collector.db'
    assert config.max_posts == 25
    assert config.collection_ttl_seconds == 60
    assert config.stale_after_seconds == 600
    assert config.request_timeout_ms == 8000
    assert config.collection_deadline_ms == 25000
    assert config.log_level == 'info'
    assert config.term_protocol == 'reddit-subreddit'


def test_uses_a_separate_database_file_in_fixture_mode():
    assert load_config({'COLLECTOR_MODE': 'fixture'}).db_path == './data/fixture.db'


def test_lets_an_explicit_db_path_win_over_the_fixture_default():
    config = load_config({'COLLECTOR_MODE': 'fixture', 'DB_PATH': '/tmp/x.db'})
    assert config.db_path == '/tmp/x.db'


def test_parses_numeric_values_from_strings():
    config = load_config({'PORT': '4000', 'COLLECTION_TTL_SECONDS': '0'})
    assert (config.port, config.collection_ttl_seconds) == (4000, 0)


def test_treats_empty_values_as_unset():
    assert load_config({'PORT': '', 'DB_PATH': ''}).port == 3001


def test_accepts_port_zero_which_lets_the_os_pick_a_free_port():
    assert load_config({'PORT': '0'}).port == 0


@pytest.mark.parametrize(
    ('env', 'variable'),
    [
        ({'PORT': '70000'}, 'PORT'),
        ({'PORT': 'abc'}, 'PORT'),
        ({'COLLECTOR_MODE': 'browser'}, 'COLLECTOR_MODE'),
        ({'MAX_POSTS': '0'}, 'MAX_POSTS'),
        ({'LOG_LEVEL': 'loud'}, 'LOG_LEVEL'),
        ({'TERM_PROTOCOL': 'nope'}, 'TERM_PROTOCOL'),
        ({'TERM_PROTOCOL': 'Reddit-Subreddit'}, 'TERM_PROTOCOL'),
        ({'REQUEST_TIMEOUT_MS': '20000', 'COLLECTION_DEADLINE_MS': '20000'}, 'REQUEST_TIMEOUT_MS'),
    ],
)
def test_rejects_invalid_values_with_a_message_naming_the_variable(env, variable):
    with pytest.raises(ConfigError, match=f'Invalid configuration: .*{variable}'):
        load_config(env)


def test_accepts_a_known_term_protocol():
    assert load_config({'TERM_PROTOCOL': 'reddit-subreddit'}).term_protocol == 'reddit-subreddit'


def test_an_empty_term_protocol_falls_back_to_the_default():
    assert load_config({'TERM_PROTOCOL': ''}).term_protocol == 'reddit-subreddit'


def test_returns_an_immutable_config():
    config = load_config({})
    with pytest.raises(dataclasses.FrozenInstanceError):
        config.port = 1  # type: ignore[misc]
