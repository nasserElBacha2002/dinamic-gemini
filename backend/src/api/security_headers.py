"""HTTP security headers and CORS origin policy helpers — Phase 4."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

# Explicit method/header allowlists — avoid ``*`` with credentialed CORS.
SAFE_CORS_ALLOW_METHODS: list[str] = [
    "GET",
    "POST",
    "PUT",
    "PATCH",
    "DELETE",
    "OPTIONS",
    "HEAD",
]
SAFE_CORS_ALLOW_HEADERS: list[str] = [
    "Accept",
    "Accept-Language",
    "Authorization",
    "Content-Type",
    "X-API-Key",
    "X-Request-Id",
    "X-Correlation-Id",
]


def normalize_cors_allow_origins(raw: str | None, *, allow_credentials: bool) -> list[str]:
    """Parse CORS origins; reject wildcard when credentials are enabled."""
    origins = [o.strip() for o in (raw or "").split(",") if o.strip()]
    if not origins:
        origins = ["http://localhost:5173", "http://127.0.0.1:5173"]
    if allow_credentials and any(o == "*" for o in origins):
        raise ValueError(
            "CORS_ALLOW_ORIGINS must not include '*' when allow_credentials=True "
            "(credentialed wildcard CORS is forbidden)."
        )
    return origins


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add baseline browser hardening headers (CSP left to FE hosting when needed)."""

    def __init__(self, app: ASGIApp, *, enable_hsts: bool = False) -> None:
        super().__init__(app)
        self._enable_hsts = enable_hsts

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=(), payment=()",
        )
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        if self._enable_hsts:
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return response
