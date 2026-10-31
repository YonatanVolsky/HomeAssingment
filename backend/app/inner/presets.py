"""What a deployment can choose for the inner server, with SERVER and INNER_ROUTES."""

from collections.abc import Mapping
from types import MappingProxyType

from app.inner.server import ThreadPoolServer

DEFAULT_SERVER = 'threadpool'
SERVER_PRESETS: Mapping[str, type] = MappingProxyType({'threadpool': ThreadPoolServer})

# Resource name on the wire -> handler name (see composition.build_inner).
DEFAULT_INNER_ROUTES = 'collector'
INNER_ROUTE_PRESETS: Mapping[str, Mapping[str, str]] = MappingProxyType(
    {'collector': MappingProxyType({'posts': 'posts', 'health': 'health'})}
)
