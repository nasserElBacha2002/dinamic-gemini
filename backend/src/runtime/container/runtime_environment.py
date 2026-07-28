"""Runtime environment classification for repository-backend policy (Phase 2)."""

from __future__ import annotations

import os
from enum import Enum


class RuntimeEnvironment(str, Enum):
    TEST = "test"
    LOCAL = "local"
    DEVELOPMENT = "development"
    STAGING = "staging"
    PREPRODUCTION = "preproduction"
    PRODUCTION = "production"
    UNKNOWN = "unknown"


_PRODUCTION_LIKE: frozenset[str] = frozenset(
    {
        "prod",
        "production",
        "live",
        "prd",
        "stg",
        "staging",
        "demo",
        "uat",
        "preproduction",
        "preprod",
    }
)
_TEST_TOKENS: frozenset[str] = frozenset({"test", "testing", "pytest", "ci"})
_LOCAL_TOKENS: frozenset[str] = frozenset({"local", "localhost"})
_DEV_TOKENS: frozenset[str] = frozenset({"dev", "development"})


def resolve_runtime_environment() -> RuntimeEnvironment:
    """Classify runtime from ``APP_ENV`` / ``ENVIRONMENT`` / ``NODE_ENV``.

    First matching non-empty token wins (APP_ENV, then ENVIRONMENT, then NODE_ENV).
    Pytest process (``PYTEST_CURRENT_TEST`` / ``PYTEST_VERSION``) → TEST when no explicit env.
    Unknown or unset → :attr:`RuntimeEnvironment.UNKNOWN` (safe default: requires SQL).
    """
    for key in ("APP_ENV", "ENVIRONMENT", "NODE_ENV"):
        raw = os.getenv(key)
        if raw is None:
            continue
        token = raw.strip().lower()
        if not token:
            continue
        if token in _TEST_TOKENS:
            return RuntimeEnvironment.TEST
        if token in _LOCAL_TOKENS:
            return RuntimeEnvironment.LOCAL
        if token in _DEV_TOKENS:
            return RuntimeEnvironment.DEVELOPMENT
        if token in {"stg", "staging"}:
            return RuntimeEnvironment.STAGING
        if token in {"preproduction", "preprod"}:
            return RuntimeEnvironment.PREPRODUCTION
        if token in {"prod", "production", "live", "prd", "demo", "uat"}:
            return RuntimeEnvironment.PRODUCTION
        return RuntimeEnvironment.UNKNOWN
    # Intentional test process without APP_ENV → allow MEMORY_ONLY for unit suites.
    if os.getenv("PYTEST_CURRENT_TEST") or os.getenv("PYTEST_VERSION"):
        return RuntimeEnvironment.TEST
    return RuntimeEnvironment.UNKNOWN


def is_production_like_runtime() -> bool:
    """True for hosted / shared deployments (production, staging, uat, …)."""
    env = resolve_runtime_environment()
    if env in (
        RuntimeEnvironment.PRODUCTION,
        RuntimeEnvironment.STAGING,
        RuntimeEnvironment.PREPRODUCTION,
    ):
        return True
    for key in ("APP_ENV", "ENVIRONMENT", "NODE_ENV"):
        raw = os.getenv(key)
        if raw is None:
            continue
        token = raw.strip().lower()
        if token and token in _PRODUCTION_LIKE:
            return True
    return False


def allows_memory_only(env: RuntimeEnvironment | None = None) -> bool:
    """MEMORY_ONLY is only intentional for test / local / development."""
    e = env if env is not None else resolve_runtime_environment()
    return e in (
        RuntimeEnvironment.TEST,
        RuntimeEnvironment.LOCAL,
        RuntimeEnvironment.DEVELOPMENT,
    )


def allows_memory_fallback(env: RuntimeEnvironment | None = None) -> bool:
    """MEMORY_FALLBACK never allowed on shared/prod-like or unknown environments."""
    e = env if env is not None else resolve_runtime_environment()
    return e in (
        RuntimeEnvironment.TEST,
        RuntimeEnvironment.LOCAL,
        RuntimeEnvironment.DEVELOPMENT,
    )


def requires_sql(env: RuntimeEnvironment | None = None) -> bool:
    """Unknown and hosted environments must use SQL (fail-fast if unavailable)."""
    return not allows_memory_only(env)


class RepositoryBackendForbiddenError(RuntimeError):
    """Raised when MEMORY_ONLY / MEMORY_FALLBACK is requested in a forbidden environment."""

    def __init__(self, message: str, *, mode: str, environment: str) -> None:
        super().__init__(message)
        self.mode = mode
        self.environment = environment
