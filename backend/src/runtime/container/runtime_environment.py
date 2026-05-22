"""Production-like runtime detection from common environment variables (Phase C5).

``AppSettings`` does not currently expose a single ``environment`` field; operators
typically set ``APP_ENV``, ``ENVIRONMENT``, or ``NODE_ENV`` in hosted deployments.
The token set aligns with ``src.env_settings.sqlserver_pytest_policy`` (hosted /
non-local names) so policy stays consistent across safety checks.

If none of these variables are set to a production-like value, the runtime is
treated as **non-production** for default in-memory fallback policy (developer-
friendly). Hosted deployments should set ``APP_ENV=production`` (or equivalent)
so that unset ``V3_ALLOW_IN_MEMORY_FALLBACK`` defaults to fail-fast when SQL is
unreachable.
"""

from __future__ import annotations

import os

_PRODUCTION_LIKE_ENV_ALIASES: frozenset[str] = frozenset(
    {"prod", "production", "live", "prd", "stg", "staging", "demo", "uat"}
)


def is_production_like_runtime() -> bool:
    """Return True when ``APP_ENV``, ``ENVIRONMENT``, or ``NODE_ENV`` indicates a hosted deployment."""
    for key in ("APP_ENV", "ENVIRONMENT", "NODE_ENV"):
        raw = os.getenv(key)
        if raw is None:
            continue
        token = raw.strip().lower()
        if token and token in _PRODUCTION_LIKE_ENV_ALIASES:
            return True
    return False
