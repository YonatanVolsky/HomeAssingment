import json
import logging
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictStr, ValidationError

from app.clock import Clock
from app.collector.types import Collector
from app.config import Config
from app.contracts import CollectionResponse
from app.db.repository import Repository
from app.errors import AppError, to_error_body
from app.services.collection_service import CollectionService
from app.terms.normalizer import Normalizer

BODY_LIMIT_BYTES = 1024
_MAX_TERM_LENGTH = 200

logger = logging.getLogger('app.api')


class CollectRequest(BaseModel):
    model_config = ConfigDict(extra='ignore')

    term: Annotated[StrictStr, Field(min_length=1, max_length=_MAX_TERM_LENGTH)]
    force: StrictBool = False


def build_app(
    *,
    repository: Repository,
    collector: Collector,
    normalizer: Normalizer,
    clock: Clock,
    config: Config,
    static_dir: Path | None = None,
) -> FastAPI:
    """Builds the HTTP app from injected dependencies, so tests need no network and no port."""
    app = FastAPI(title='Reddit Collector', docs_url='/api/docs', openapi_url='/api/openapi.json')
    service = CollectionService(
        repository=repository,
        collector=collector,
        normalizer=normalizer,
        clock=clock,
        max_posts=config.max_posts,
        ttl_seconds=config.collection_ttl_seconds,
        logger=logger,
    )

    @app.exception_handler(AppError)
    async def handle_app_error(_request: Request, error: AppError) -> JSONResponse:
        return _error_response(error)

    @app.exception_handler(Exception)
    async def handle_unexpected(_request: Request, error: Exception) -> JSONResponse:
        logger.error('unhandled error', exc_info=error)
        return _error_response(AppError('INTERNAL', cause=error))

    @app.get('/api/health')
    async def health() -> JSONResponse:
        body: dict[str, Any] = {
            'collectorMode': config.collector_mode,
            'staleAfterSeconds': config.stale_after_seconds,
        }
        try:
            repository.ping()
        except AppError as error:
            logger.error('health check: database unavailable', exc_info=error)
            return JSONResponse({'status': 'error', 'db': 'error', **body}, status_code=503)
        return JSONResponse({'status': 'ok', 'db': 'ok', **body})

    @app.post('/api/collections')
    async def collect(request: Request) -> JSONResponse:
        payload = await request.body()
        if len(payload) > BODY_LIMIT_BYTES:
            raise AppError('INVALID_TERM')
        try:
            parsed = CollectRequest.model_validate(json.loads(payload))
        except (ValueError, ValidationError) as error:
            raise AppError('INVALID_TERM', cause=error) from error
        try:
            response = await service.collect(parsed.term, parsed.force)
        except AppError as error:
            if error.code == 'INVALID_TERM':
                raise
            logger.warning('collection for %r failed: %s', parsed.term, error.code)
            return _error_response(error, service.last_good(parsed.term))
        return _json(response)

    @app.get('/api/posts')
    async def posts(term: str | None = None) -> JSONResponse:
        if term is None or len(term) > _MAX_TERM_LENGTH:
            raise AppError('INVALID_TERM')
        return _json(service.get_posts(term))

    if static_dir is not None and (static_dir / 'index.html').is_file():
        _serve_frontend(app, static_dir.resolve())

    return app


def _json(response: CollectionResponse) -> JSONResponse:
    return JSONResponse(response.model_dump(by_alias=True))


def _error_response(error: AppError, last_good: CollectionResponse | None = None) -> JSONResponse:
    body: dict[str, Any] = {'error': to_error_body(error)}
    if last_good is not None:
        body['lastGood'] = last_good.model_dump(by_alias=True)
    headers = {}
    if error.retry_after_seconds is not None:
        headers['Retry-After'] = str(error.retry_after_seconds)
    return JSONResponse(body, status_code=error.http_status, headers=headers)


def _serve_frontend(app: FastAPI, root: Path) -> None:
    """Serves the built UI (production-like run). Unknown paths get index.html (client routes)."""

    @app.get('/{path:path}', include_in_schema=False)
    async def frontend(path: str) -> Response:
        if path.startswith('api/'):
            return JSONResponse({'message': 'Not found'}, status_code=404)
        candidate = (root / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(root):
            return FileResponse(candidate)
        return FileResponse(root / 'index.html')
