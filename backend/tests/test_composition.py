from types import MappingProxyType

import pytest

from app import composition
from app.composition import build_inner, create_term_normalizer
from app.config import ConfigError, load_config
from tests.helpers import make_logger


def test_create_term_normalizer_uses_the_configured_preset():
    assert create_term_normalizer(load_config({})).normalize('r/Ubisoft') == 'ubisoft'


def test_build_inner_refuses_a_route_to_a_missing_handler(tmp_path, monkeypatch):
    monkeypatch.setattr(
        composition, 'INNER_ROUTE_PRESETS', MappingProxyType({'collector': {'posts': 'nope'}})
    )
    config = load_config({'DB_PATH': str(tmp_path / 'x.db'), 'INNER_PORT': '0'})
    with pytest.raises(ConfigError, match='nope'):
        build_inner(config, logger=make_logger())
