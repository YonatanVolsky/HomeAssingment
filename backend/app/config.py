"""Environment configuration, parsed once at startup. Nothing else reads os.environ."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    ValidationInfo,
    field_validator,
    model_validator,
)

from app.inner.presets import (
    DEFAULT_INNER_ROUTES,
    DEFAULT_SERVER,
    INNER_ROUTE_PRESETS,
    SERVER_PRESETS,
)
from app.terms.presets import DEFAULT_PRESET, PRESETS

CollectorMode = Literal['live', 'fixture']
LogLevel = Literal['critical', 'error', 'warning', 'info', 'debug']


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Config:
    port: int
    host: str
    collector_mode: CollectorMode
    db_path: str
    max_posts: int
    collection_ttl_seconds: int
    stale_after_seconds: int
    request_timeout_ms: int
    collection_deadline_ms: int
    log_level: LogLevel
    term_protocol: str
    inner_host: str
    inner_port: int
    server: str
    server_threads: int
    inner_routes: str


# Settings whose value must name a preset defined in code.
_PRESET_CHOICES = {
    'TERM_PROTOCOL': PRESETS,
    'SERVER': SERVER_PRESETS,
    'INNER_ROUTES': INNER_ROUTE_PRESETS,
}


class _Env(BaseModel):
    model_config = ConfigDict(extra='ignore')

    PORT: Annotated[int, Field(ge=0, le=65535)] = 3001
    HOST: Annotated[str, Field(min_length=1)] = '127.0.0.1'
    COLLECTOR_MODE: CollectorMode = 'live'
    DB_PATH: str | None = None
    MAX_POSTS: Annotated[int, Field(ge=1, le=100)] = 25
    COLLECTION_TTL_SECONDS: Annotated[int, Field(ge=0, le=3600)] = 60
    STALE_AFTER_SECONDS: Annotated[int, Field(ge=1, le=7 * 24 * 3600)] = 600
    REQUEST_TIMEOUT_MS: Annotated[int, Field(ge=1000, le=20000)] = 8000
    COLLECTION_DEADLINE_MS: Annotated[int, Field(ge=5000, le=60000)] = 25000
    LOG_LEVEL: LogLevel = 'info'
    TERM_PROTOCOL: str = DEFAULT_PRESET
    INNER_HOST: Annotated[str, Field(min_length=1)] = '127.0.0.1'
    INNER_PORT: Annotated[int, Field(ge=0, le=65535)] = 3002
    SERVER: str = DEFAULT_SERVER
    SERVER_THREADS: Annotated[int, Field(ge=1, le=64)] = 8
    INNER_ROUTES: str = DEFAULT_INNER_ROUTES

    @field_validator(*_PRESET_CHOICES)
    @classmethod
    def _known_preset(cls, value: str, info: ValidationInfo) -> str:
        choices = _PRESET_CHOICES[info.field_name]
        if value not in choices:
            raise ValueError(f'must be one of: {", ".join(choices)}')
        return value

    @model_validator(mode='after')
    def _timeout_below_deadline(self) -> '_Env':
        if self.REQUEST_TIMEOUT_MS >= self.COLLECTION_DEADLINE_MS:
            raise ValueError('REQUEST_TIMEOUT_MS must be below COLLECTION_DEADLINE_MS')
        return self


def load_config(env: Mapping[str, str]) -> Config:
    """Empty strings count as unset, so a blank line in a .env file falls back to the default."""
    present = {key: value for key, value in env.items() if value != ''}
    try:
        e = _Env.model_validate(present)
    except ValidationError as error:
        problems = '; '.join(
            f'{".".join(str(p) for p in issue["loc"]) or "config"}: {issue["msg"]}'
            for issue in error.errors()
        )
        raise ConfigError(f'Invalid configuration: {problems}') from None

    default_db = './data/fixture.db' if e.COLLECTOR_MODE == 'fixture' else './data/collector.db'
    return Config(
        port=e.PORT,
        host=e.HOST,
        collector_mode=e.COLLECTOR_MODE,
        db_path=e.DB_PATH or default_db,
        max_posts=e.MAX_POSTS,
        collection_ttl_seconds=e.COLLECTION_TTL_SECONDS,
        stale_after_seconds=e.STALE_AFTER_SECONDS,
        request_timeout_ms=e.REQUEST_TIMEOUT_MS,
        collection_deadline_ms=e.COLLECTION_DEADLINE_MS,
        log_level=e.LOG_LEVEL,
        term_protocol=e.TERM_PROTOCOL,
        inner_host=e.INNER_HOST,
        inner_port=e.INNER_PORT,
        server=e.SERVER,
        server_threads=e.SERVER_THREADS,
        inner_routes=e.INNER_ROUTES,
    )
