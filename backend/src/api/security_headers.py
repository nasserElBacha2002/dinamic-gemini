"""HTTP security headers and CORS origin policy helpers — Phase 4."""

from __future__ import annotations

import os
from collections.abc import Awaitable, Callable
from urllib.parse import urlparse

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from src.runtime.container.runtime_environment import (
    RuntimeEnvironment,
    resolve_runtime_environment,
)

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
    "X-Idempotency-Key",
]


class CorsPolicyError(ValueError):
    """Invalid CORS configuration for the resolved runtime."""


def _is_local_like(env: RuntimeEnvironment) -> bool:
    return env in (
        RuntimeEnvironment.TEST,
        RuntimeEnvironment.LOCAL,
        RuntimeEnvironment.DEVELOPMENT,
    )


def normalize_cors_allow_origins(
    raw: str | None,
    *,
    allow_credentials: bool,
    env: RuntimeEnvironment | None = None,
) -> list[str]:
    """Parse CORS origins with production-like fail-safe rules."""
    e = env if env is not None else resolve_runtime_environment()
    origins = [o.strip() for o in (raw or "").split(",") if o.strip()]
    seen: set[str] = set()
    deduped: list[str] = []
    for o in origins:
        if o not in seen:
            seen.add(o)
            deduped.append(o)
    origins = deduped

    if not origins:
        if _is_local_like(e):
            return ["http://localhost:5173", "http://127.0.0.1:5173"]
        raise CorsPolicyError(
            "CORS_ALLOW_ORIGINS is required in hosted runtimes "
            f"(resolved={e.value}); localhost defaults are not applied."
        )

    if allow_credentials and any(o == "*" for o in origins):
        raise CorsPolicyError(
            "CORS_ALLOW_ORIGINS must not include '*' when allow_credentials=True "
            "(credentialed wildcard CORS is forbidden)."
        )
    if any(o.lower() == "null" for o in origins):
        raise CorsPolicyError("CORS_ALLOW_ORIGINS must not include the 'null' origin.")

    if not _is_local_like(e):
        for o in origins:
            parsed = urlparse(o)
            if parsed.scheme != "https":
                raise CorsPolicyError(f"Hosted CORS origins must use https (got {o!r}).")
            host = (parsed.hostname or "").lower()
            if host in ("localhost", "127.0.0.1", "::1") or host.endswith(".localhost"):
                raise CorsPolicyError(
                    f"Hosted CORS origins must not use localhost (got {o!r})."
                )
            if o == "*":
                raise CorsPolicyError("Hosted CORS origins must not use wildcard '*'.")
    return origins


def resolve_hsts_enabled(
    *,
    env: RuntimeEnvironment | None = None,
    enable_hsts_env: str | None = None,
    forwarded_trusted_hosts: str | None = None,
) -> tuple[bool, int]:
    """HSTS only for hosted runtimes when explicitly enabled and a trusted proxy is set."""
    e = env if env is not None else resolve_runtime_environment()
    raw_src = enable_hsts_env if enable_hsts_env is not None else (os.getenv("ENABLE_HSTS") or "")
    raw = raw_src.strip().lower()
    try:
        max_age = int((os.getenv("HSTS_MAX_AGE_SEC") or "31536000").strip() or "31536000")
    except ValueError:
        max_age = 31536000
    if max_age < 0:
        max_age = 0
    if raw not in ("1", "true", "yes", "on"):
        return False, max_age
    if _is_local_like(e):
        return False, max_age
    forwarded = (
        forwarded_trusted_hosts
        if forwarded_trusted_hosts is not None
        else (os.getenv("FORWARDED_TRUSTED_HOSTS") or "")
    ).strip()
    if not forwarded:
        return False, max_age
    return True, max_age


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add baseline browser hardening headers (CSP left to FE hosting when needed)."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        enable_hsts: bool = False,
        hsts_max_age_sec: int = 31536000,
    ) -> None:
        super().__init__(app)
        self._enable_hsts = enable_hsts
        self._hsts_max_age_sec = hsts_max_age_sec

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
        if self._enable_hsts and self._hsts_max_age_sec > 0:
            response.headers.setdefault(
                "Strict-Transport-Security",
                f"max-age={self._hsts_max_age_sec}; includeSubDomains",
            )
        return response
