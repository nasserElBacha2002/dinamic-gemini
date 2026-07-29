"""API key enforcement helpers — Model A (JWT for public clients).

Public browser/mobile clients authenticate with JWT only.
``X-API-Key`` is optional and applies only to configured path prefixes
(e.g. ``/api/v3/admin``) when ``API_KEY`` is set — never required globally.
"""

from __future__ import annotations

import hashlib
import secrets

# Liveness/readiness and OpenAPI must never require an API key.
API_KEY_BYPASS_EXACT_PATHS: frozenset[str] = frozenset(
    {
        "/health",
        "/ready",
        "/metrics",
        "/docs",
        "/redoc",
        "/openapi.json",
    }
)


def parse_api_key_path_prefixes(raw: str | None) -> list[str]:
    """Comma-separated path prefixes; empty → no HTTP API-key enforcement (Model A default)."""
    return [p.strip() for p in (raw or "").split(",") if p.strip()]


def path_requires_api_key(path: str, prefixes: list[str]) -> bool:
    if path in API_KEY_BYPASS_EXACT_PATHS:
        return False
    if not prefixes:
        return False
    return any(path == p or path.startswith(p.rstrip("/") + "/") or path.startswith(p) for p in prefixes)


def api_keys_match(provided: str, expected: str) -> bool:
    """Constant-time compare via SHA-256 digests (equal length)."""
    return secrets.compare_digest(
        hashlib.sha256(provided.encode("utf-8")).digest(),
        hashlib.sha256(expected.encode("utf-8")).digest(),
    )
