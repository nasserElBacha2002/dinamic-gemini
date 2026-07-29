"""Phase 5 — authorization for GET /metrics."""

from __future__ import annotations

from starlette.requests import Request

from src.api.api_key_policy import api_keys_match
from src.runtime.container.runtime_environment import (
    RuntimeEnvironment,
    resolve_runtime_environment,
)


def _is_loopback(request: Request) -> bool:
    client = request.client
    if client is None:
        return False
    host = (client.host or "").strip().lower()
    return host in {"127.0.0.1", "::1", "localhost", "testclient"}


def metrics_access_allowed(
    request: Request,
    *,
    api_key: str,
    auth_mode: str,
    env: RuntimeEnvironment | None = None,
) -> bool:
    """Return True when the caller may scrape /metrics."""
    mode = (auth_mode or "api_key").strip().lower()
    e = env if env is not None else resolve_runtime_environment()
    local_like = e in (
        RuntimeEnvironment.TEST,
        RuntimeEnvironment.LOCAL,
        RuntimeEnvironment.DEVELOPMENT,
    )

    if mode == "open":
        return local_like

    if mode == "loopback":
        return _is_loopback(request)

    # Default: api_key
    expected = (api_key or "").strip()
    if expected:
        provided = (request.headers.get("X-API-Key") or "").strip()
        return api_keys_match(provided, expected)
    # No API_KEY configured: allow only local-like + loopback (never open hosted).
    return local_like and _is_loopback(request)
