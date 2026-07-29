"""Phase 5 — HTTP request ID + metrics middleware."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Match
from starlette.types import ASGIApp

from src.observability.context import bind_request_ids, reset_request_ids
from src.observability.metrics.instruments import (
    HTTP_REQUESTS_IN_PROGRESS,
    observe_http_request,
)
from src.observability.metrics.registry import get_metrics_registry
from src.observability.request_ids import (
    generate_correlation_id,
    generate_request_id,
    normalize_inbound_id,
)

_SKIP_METRIC_PATHS = frozenset({"/metrics", "/health", "/ready"})


def resolve_route_template(request: Request) -> str:
    """Prefer FastAPI/Starlette route path template (no UUID cardinality)."""
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    if isinstance(path, str) and path:
        return path
    app = request.app
    router = getattr(app, "router", None)
    if router is not None:
        for r in getattr(router, "routes", []):
            match, _ = r.matches(request.scope)
            if match == Match.FULL:
                p = getattr(r, "path", None)
                if isinstance(p, str) and p:
                    return p
    raw = request.url.path or "/"
    parts: list[str] = []
    for seg in raw.split("/"):
        if not seg:
            continue
        if len(seg) >= 32 and all(c in "0123456789abcdefABCDEF-" for c in seg):
            parts.append("{id}")
        else:
            parts.append(seg)
    return "/" + "/".join(parts) if parts else "/"


def status_class(status_code: int) -> str:
    if 100 <= status_code < 200:
        return "1xx"
    if 200 <= status_code < 300:
        return "2xx"
    if 300 <= status_code < 400:
        return "3xx"
    if 400 <= status_code < 500:
        return "4xx"
    return "5xx"


class ObservabilityMiddleware(BaseHTTPMiddleware):
    """Bind request/correlation IDs and record low-cardinality HTTP metrics."""

    def __init__(self, app: ASGIApp, *, metrics_enabled: bool = True) -> None:
        super().__init__(app)
        self._metrics_enabled = metrics_enabled

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = normalize_inbound_id(
            request.headers.get("X-Request-ID") or request.headers.get("X-Request-Id"),
            fallback=generate_request_id(),
        )
        correlation_id = normalize_inbound_id(
            request.headers.get("X-Correlation-ID")
            or request.headers.get("X-Correlation-Id"),
            fallback=generate_correlation_id(),
        )
        tokens = bind_request_ids(request_id=request_id, correlation_id=correlation_id)
        path = request.url.path or "/"
        track = self._metrics_enabled and path not in _SKIP_METRIC_PATHS
        route_template = "pending"
        method = request.method.upper()
        started = time.perf_counter()
        reg = get_metrics_registry()
        if track:
            reg.inc_gauge(
                HTTP_REQUESTS_IN_PROGRESS,
                "In-flight HTTP requests",
                {"method": method, "route_template": "in_flight"},
                1.0,
            )
        try:
            response = await call_next(request)
        except Exception:
            if track:
                route_template = resolve_route_template(request)
                observe_http_request(
                    method=method,
                    route_template=route_template,
                    status_class="5xx",
                    duration_seconds=time.perf_counter() - started,
                )
                reg.inc_gauge(
                    HTTP_REQUESTS_IN_PROGRESS,
                    "In-flight HTTP requests",
                    {"method": method, "route_template": "in_flight"},
                    -1.0,
                )
            reset_request_ids(tokens)
            raise
        else:
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Correlation-ID"] = correlation_id
            if track:
                route_template = resolve_route_template(request)
                observe_http_request(
                    method=method,
                    route_template=route_template,
                    status_class=status_class(response.status_code),
                    duration_seconds=time.perf_counter() - started,
                )
                reg.inc_gauge(
                    HTTP_REQUESTS_IN_PROGRESS,
                    "In-flight HTTP requests",
                    {"method": method, "route_template": "in_flight"},
                    -1.0,
                )
            reset_request_ids(tokens)
            return response
