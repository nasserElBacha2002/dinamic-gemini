"""Phase 2 — repository backend policy (MEMORY_ONLY / MEMORY_FALLBACK / unknown env)."""

from __future__ import annotations

import os

import pytest

import src.config as config_module
from src.config import load_settings
from src.runtime.app_container import AppContainer
from src.runtime.container.repository_backend import (
    RepositoryBackendMode,
    resolve_repository_backend_mode,
)
from src.runtime.container.runtime_environment import (
    RepositoryBackendForbiddenError,
    RuntimeEnvironment,
    allows_memory_fallback,
    allows_memory_only,
    requires_sql,
    resolve_runtime_environment,
)


@pytest.mark.parametrize(
    ("token", "expected"),
    [
        ("test", RuntimeEnvironment.TEST),
        ("local", RuntimeEnvironment.LOCAL),
        ("development", RuntimeEnvironment.DEVELOPMENT),
        ("stage", RuntimeEnvironment.STAGING),
        ("stg", RuntimeEnvironment.STAGING),
        ("staging", RuntimeEnvironment.STAGING),
        ("production", RuntimeEnvironment.PRODUCTION),
        ("prod", RuntimeEnvironment.PRODUCTION),
        ("uat", RuntimeEnvironment.PRODUCTION),
        ("preprod", RuntimeEnvironment.PREPRODUCTION),
        ("preproduction", RuntimeEnvironment.PREPRODUCTION),
        ("mystery", RuntimeEnvironment.UNKNOWN),
    ],
)
def test_resolve_runtime_environment_tokens(
    monkeypatch: pytest.MonkeyPatch, token: str, expected: RuntimeEnvironment
) -> None:
    for k in (
        "V3_RUNTIME_ENVIRONMENT",
        "DINAMIC_RUNTIME_PROFILE",
        "APP_ENV",
        "ENVIRONMENT",
        "NODE_ENV",
    ):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("APP_ENV", token)
    assert resolve_runtime_environment() is expected


def test_v3_runtime_environment_takes_precedence_over_pytest_heuristic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Explicit ``V3_RUNTIME_ENVIRONMENT`` must win even though pytest sets ``PYTEST_VERSION``."""
    for k in (
        "V3_RUNTIME_ENVIRONMENT",
        "DINAMIC_RUNTIME_PROFILE",
        "APP_ENV",
        "ENVIRONMENT",
        "NODE_ENV",
    ):
        monkeypatch.delenv(k, raising=False)
    assert os.getenv("PYTEST_VERSION") or os.getenv("PYTEST_CURRENT_TEST")
    monkeypatch.setenv("V3_RUNTIME_ENVIRONMENT", "production")
    assert resolve_runtime_environment() is RuntimeEnvironment.PRODUCTION


def test_dinamic_runtime_profile_takes_precedence_over_pytest_heuristic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for k in (
        "V3_RUNTIME_ENVIRONMENT",
        "DINAMIC_RUNTIME_PROFILE",
        "APP_ENV",
        "ENVIRONMENT",
        "NODE_ENV",
    ):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("DINAMIC_RUNTIME_PROFILE", "staging")
    assert resolve_runtime_environment() is RuntimeEnvironment.STAGING


def test_pytest_heuristic_only_applies_when_no_explicit_env_token_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for k in (
        "V3_RUNTIME_ENVIRONMENT",
        "DINAMIC_RUNTIME_PROFILE",
        "APP_ENV",
        "ENVIRONMENT",
        "NODE_ENV",
    ):
        monkeypatch.delenv(k, raising=False)
    # No explicit token set anywhere: falls back to the pytest-process heuristic → TEST.
    assert resolve_runtime_environment() is RuntimeEnvironment.TEST


def test_unknown_and_hosted_require_sql(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "mystery")
    assert requires_sql() is True
    assert allows_memory_only() is False
    assert allows_memory_fallback() is False
    monkeypatch.setenv("APP_ENV", "staging")
    assert requires_sql() is True
    assert allows_memory_fallback() is False
    monkeypatch.setenv("APP_ENV", "development")
    assert requires_sql() is False
    assert allows_memory_only() is True


def test_memory_only_forbidden_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SQLSERVER_ENABLED", "false")
    config_module._settings = None
    settings = load_settings()
    with pytest.raises(RepositoryBackendForbiddenError):
        resolve_repository_backend_mode(
            settings=settings,
            probe_sql=lambda: None,
            allow_in_memory_fallback=lambda: False,
        )


def test_memory_only_allowed_in_development(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("SQLSERVER_ENABLED", "false")
    config_module._settings = None
    settings = load_settings()
    res = resolve_repository_backend_mode(
        settings=settings,
        probe_sql=lambda: None,
        allow_in_memory_fallback=lambda: True,
    )
    assert res.mode == RepositoryBackendMode.MEMORY_ONLY


def test_sql_runtime_error_does_not_switch_to_memory_when_fallback_disallowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SQLSERVER_ENABLED", "true")
    monkeypatch.setenv(
        "SQLSERVER_CONNECTION_STRING",
        "Driver=ODBC Driver 18 for SQL Server;Server=127.0.0.1,1;Database=x;Uid=x;Pwd=x;"
        "TrustServerCertificate=yes",
    )
    config_module._settings = None

    def _boom() -> None:
        raise TimeoutError("sql timeout")

    c = AppContainer(load_settings())
    monkeypatch.setattr(c, "_probe_sql_for_repository_backend", _boom)
    with pytest.raises(TimeoutError, match="sql timeout"):
        c._get_repository_backend_resolution()
    # Cached resolution must remain unset (no silent memory mode).
    assert c._repository_backend_resolution is None
    # Second call still fails — does not flip to memory.
    with pytest.raises(TimeoutError):
        c.get_inventory_repo()


def test_get_repository_backend_status_forbidden_mode_never_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Public status API surfaces ``RepositoryBackendForbiddenError`` as resolved=False, not a raise."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SQLSERVER_ENABLED", "false")
    config_module._settings = None
    c = AppContainer(load_settings())

    status = c.get_repository_backend_status()

    assert status.resolved is False
    assert status.healthy is False
    assert status.fallback_activated is False
    assert status.environment == "production"
    assert status.reason_code == "REPOSITORY_BACKEND_MODE_FORBIDDEN"


def test_get_repository_backend_status_probe_failure_never_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SQL probe failure with fallback disallowed → resolved=False status, not an exception."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SQLSERVER_ENABLED", "true")
    monkeypatch.setenv(
        "SQLSERVER_CONNECTION_STRING",
        "Driver=ODBC Driver 18 for SQL Server;Server=127.0.0.1,1;Database=x;Uid=x;Pwd=x;"
        "TrustServerCertificate=yes",
    )
    config_module._settings = None
    c = AppContainer(load_settings())
    monkeypatch.setattr(
        c, "_probe_sql_for_repository_backend", lambda: (_ for _ in ()).throw(TimeoutError("boom"))
    )

    status = c.get_repository_backend_status()

    assert status.resolved is False
    assert status.healthy is False
    assert status.mode is None
    assert status.reason_code == "REPOSITORY_BACKEND_RESOLUTION_FAILED"


def test_get_repository_backend_status_memory_only_allowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("SQLSERVER_ENABLED", "false")
    config_module._settings = None
    c = AppContainer(load_settings())

    status = c.get_repository_backend_status()

    assert status.resolved is True
    assert status.healthy is True
    assert status.mode == "memory_only"
    assert status.fallback_activated is False
    assert status.reason_code is None


def test_get_repository_backend_status_memory_fallback_activated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("SQLSERVER_ENABLED", "true")
    monkeypatch.setenv(
        "SQLSERVER_CONNECTION_STRING",
        "Driver=ODBC Driver 18 for SQL Server;Server=127.0.0.1,1;Database=x;Uid=x;Pwd=x;"
        "TrustServerCertificate=yes",
    )
    monkeypatch.setenv("V3_ALLOW_IN_MEMORY_FALLBACK", "true")
    config_module._settings = None
    c = AppContainer(load_settings())
    monkeypatch.setattr(
        c, "_probe_sql_for_repository_backend", lambda: (_ for _ in ()).throw(TimeoutError("boom"))
    )

    status = c.get_repository_backend_status()

    assert status.resolved is True
    assert status.healthy is True
    assert status.mode == "memory_fallback"
    assert status.fallback_activated is True
    assert status.reason_code == "SQL_PROBE_FAILED_MEMORY_FALLBACK_ACTIVE"
    # Never exposes the raw probe exception text or connection string.
    assert "boom" not in (status.reason_code or "")
    assert "Pwd=" not in (status.reason_code or "")
