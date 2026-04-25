"""Prometheus HTTP metrics middleware (M21).

Records aitpg_requests_total and aitpg_request_duration_seconds for every
HTTP response.  When the metrics registry has not been initialised the
middleware is a pass-through (zero overhead).
"""

from __future__ import annotations

import time
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp


class PrometheusMiddleware(BaseHTTPMiddleware):
    """Lightweight HTTP instrumentation middleware."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        t0 = time.perf_counter()
        response = await call_next(request)
        elapsed = time.perf_counter() - t0

        try:
            from ai_testplan_generator.telemetry import metrics as _m

            if _m._registry is not None:
                method = request.method
                path = request.url.path
                status = str(response.status_code)
                _m.requests_total().labels(method=method, path=path, status=status).inc()
                _m.request_duration_seconds().labels(method=method, path=path).observe(elapsed)
        except Exception:  # noqa: BLE001
            pass

        return response
