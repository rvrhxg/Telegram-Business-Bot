"""Minimal HTTP telemetry: never record URLs, bodies, identities or secrets."""
import json
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

logger = logging.getLogger('portfolio.http')
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(message)s'))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)


def install_observability(app: FastAPI, probe: Callable[[], None]) -> None:
    app.state.db_probe = probe

    @app.get('/api/ready')
    def ready() -> JSONResponse:
        try:
            app.state.db_probe()
            return JSONResponse({'status': 'ready'})
        except Exception:
            return JSONResponse({'status': 'unavailable'}, status_code=503)

    @app.middleware('http')
    async def telemetry(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        request_id = uuid.uuid4().hex
        started = time.perf_counter()
        failure: str | None = None
        try:
            response = await call_next(request)
        except Exception as error:
            # Error text/tracebacks may contain DB parameters or credentials.
            failure = type(error).__name__
            response = JSONResponse({'detail': 'Internal server error'}, status_code=500)
        response.headers['X-Request-ID'] = request_id
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        route = getattr(request.scope.get('route'), 'path', None) or 'unmatched'
        logger.info(json.dumps({'event': 'http_request', 'request_id': request_id,
                                'method': request.method if request.method in {'GET','HEAD','POST','PUT','PATCH','DELETE','OPTIONS'} else 'OTHER',
                                'route': route, 'status': response.status_code,
                                'duration_ms': round((time.perf_counter()-started)*1000, 2),
                                'error_type': failure}, ensure_ascii=True))
        return response
