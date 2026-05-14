"""Unit tests for :mod:`src.runtime.container.repository_backend`."""

from __future__ import annotations

import pytest

import src.config as config_module
from src.config import AppSettings, load_settings
from src.runtime.container.repository_backend import (
    RepositoryBackendMode,
    resolve_repository_backend_mode,
)


@pytest.fixture
def settings_sql_off(monkeypatch: pytest.MonkeyPatch) -> AppSettings:
    monkeypatch.setenv("SQLSERVER_ENABLED", "false")
    config_module._settings = None
    return load_settings()


@pytest.fixture
def settings_sql_on(monkeypatch: pytest.MonkeyPatch) -> AppSettings:
    monkeypatch.setenv("SQLSERVER_ENABLED", "true")
    monkeypatch.setenv(
        "SQLSERVER_CONNECTION_STRING",
        "Driver=ODBC Driver 18 for SQL Server;Server=127.0.0.1,1;Database=x;Uid=x;Pwd=x;"
        "TrustServerCertificate=yes",
    )
    config_module._settings = None
    return load_settings()


def test_resolve_memory_only_when_sql_disabled(settings_sql_off: AppSettings) -> None:
    def _probe_should_not_run() -> None:
        raise AssertionError("probe_sql must not be called when SQL target is disabled")

    r = resolve_repository_backend_mode(
        settings=settings_sql_off,
        probe_sql=_probe_should_not_run,
        allow_in_memory_fallback=lambda: True,
    )
    assert r.mode == RepositoryBackendMode.MEMORY_ONLY
    assert r.sql_enabled is False
    assert r.fallback_allowed is True
    assert r.reason


def test_resolve_sql_when_probe_succeeds(settings_sql_on: AppSettings) -> None:
    probe_ran = {"n": 0}

    def probe() -> None:
        probe_ran["n"] += 1

    r = resolve_repository_backend_mode(
        settings=settings_sql_on,
        probe_sql=probe,
        allow_in_memory_fallback=lambda: True,
    )
    assert r.mode == RepositoryBackendMode.SQL
    assert r.sql_enabled is True
    assert probe_ran["n"] == 1
    assert r.reason is None


def test_resolve_memory_fallback_when_probe_fails_and_fallback_allowed(
    settings_sql_on: AppSettings,
) -> None:
    err = ConnectionError("simulated SQL probe failure")

    def probe() -> None:
        raise err

    r = resolve_repository_backend_mode(
        settings=settings_sql_on,
        probe_sql=probe,
        allow_in_memory_fallback=lambda: True,
    )
    assert r.mode == RepositoryBackendMode.MEMORY_FALLBACK
    assert r.sql_enabled is True
    assert r.fallback_allowed is True
    assert r.reason is not None
    assert "ConnectionError" in r.reason


def test_resolve_reraises_when_probe_fails_and_fallback_disabled(
    settings_sql_on: AppSettings,
) -> None:
    def probe() -> None:
        raise ValueError("probe boom")

    with pytest.raises(ValueError, match="probe boom"):
        resolve_repository_backend_mode(
            settings=settings_sql_on,
            probe_sql=probe,
            allow_in_memory_fallback=lambda: False,
        )


def test_allow_in_memory_fallback_callable_respected(settings_sql_on: AppSettings) -> None:
    r_off = resolve_repository_backend_mode(
        settings=settings_sql_on,
        probe_sql=lambda: None,
        allow_in_memory_fallback=lambda: False,
    )
    assert r_off.fallback_allowed is False

    r_on = resolve_repository_backend_mode(
        settings=settings_sql_on,
        probe_sql=lambda: None,
        allow_in_memory_fallback=lambda: True,
    )
    assert r_on.fallback_allowed is True
