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
        "stage",
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
_STAGING_TOKENS: frozenset[str] = frozenset({"stg", "stage", "staging"})
_PREPRODUCTION_TOKENS: frozenset[str] = frozenset({"preproduction", "preprod"})
_PRODUCTION_TOKENS: frozenset[str] = frozenset({"prod", "production", "live", "prd", "demo", "uat"})

# Explicit runtime designation wins over generic app env vars, which in turn win over the
# pytest-process heuristic below. Checked in this order; first non-empty token wins.
_ENV_VAR_PRECEDENCE: tuple[str, ...] = (
    "V3_RUNTIME_ENVIRONMENT",
    "DINAMIC_RUNTIME_PROFILE",
    "APP_ENV",
    "ENVIRONMENT",
    "NODE_ENV",
)


def resolve_runtime_environment() -> RuntimeEnvironment:
    """Classify runtime from explicit env vars, falling back to a pytest-process heuristic.

    First matching non-empty token wins, checked in :data:`_ENV_VAR_PRECEDENCE` order:
    ``V3_RUNTIME_ENVIRONMENT``, ``DINAMIC_RUNTIME_PROFILE`` (explicit runtime designations),
    then the generic ``APP_ENV`` / ``ENVIRONMENT`` / ``NODE_ENV``.

    ``PYTEST_CURRENT_TEST`` / ``PYTEST_VERSION`` are used **only** as a last-resort fallback
    when none of the above env vars are set — they must never override an explicit token
    (e.g. a test that sets ``V3_RUNTIME_ENVIRONMENT=production`` to exercise production policy
    must resolve to PRODUCTION, not TEST, even though it runs under pytest).

    Unknown or unset → :attr:`RuntimeEnvironment.UNKNOWN` (safe default: requires SQL).
    """
    for key in _ENV_VAR_PRECEDENCE:
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
        if token in _STAGING_TOKENS:
            return RuntimeEnvironment.STAGING
        if token in _PREPRODUCTION_TOKENS:
            return RuntimeEnvironment.PREPRODUCTION
        if token in _PRODUCTION_TOKENS:
            return RuntimeEnvironment.PRODUCTION
        return RuntimeEnvironment.UNKNOWN
    # No explicit env token set anywhere — fall back to detecting an intentional pytest
    # process so unit suites default to TEST (allows MEMORY_ONLY) instead of UNKNOWN.
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
