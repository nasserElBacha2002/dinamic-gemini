"""Phase 2 — repository backend policy (MEMORY_ONLY / MEMORY_FALLBACK / unknown env)."""

from __future__ import annotations

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
        ("staging", RuntimeEnvironment.STAGING),
        ("production", RuntimeEnvironment.PRODUCTION),
        ("preprod", RuntimeEnvironment.PREPRODUCTION),
        ("mystery", RuntimeEnvironment.UNKNOWN),
    ],
)
def test_resolve_runtime_environment_tokens(
    monkeypatch: pytest.MonkeyPatch, token: str, expected: RuntimeEnvironment
) -> None:
    for k in ("APP_ENV", "ENVIRONMENT", "NODE_ENV"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("APP_ENV", token)
    assert resolve_runtime_environment() is expected


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
