"""Regression: pytest .env.test must not be clobbered by reload_settings() / developer .env."""

from __future__ import annotations

import re

import pytest

from src.env_settings.sqlserver_resolution import (
    resolve_sqlserver_connection_config,
    resolved_sqlserver_database_name_from_env,
)


def test_pytest_dotenv_lock_survives_reload_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DINAMIC_PYTEST_DOTENV_LOCKED", "1")
    monkeypatch.setenv("SQLSERVER_CONNECTION_STRING", "")
    monkeypatch.setenv("SQLSERVER_SERVER", "localhost")
    monkeypatch.setenv("SQLSERVER_DATABASE", "dinamic_inventory_test")
    monkeypatch.setenv("SQLSERVER_UID", "sa")
    monkeypatch.setenv("SQLSERVER_PWD", "test-password")
    monkeypatch.setenv("SQLSERVER_DRIVER", "ODBC Driver 17 for SQL Server")
    monkeypatch.setenv("SQLSERVER_TRUST_SERVER_CERTIFICATE", "yes")

    from src.config import reload_settings

    reload_settings()
    assert resolved_sqlserver_database_name_from_env() == "dinamic_inventory_test"
    cs = resolve_sqlserver_connection_config().connection_string
    match = re.search(r"DATABASE=([^;]+)", cs, flags=re.I)
    assert match is not None
    assert match.group(1) == "dinamic_inventory_test"


def test_conftest_sets_pytest_dotenv_lock() -> None:
    import os

    assert (os.getenv("DINAMIC_PYTEST_DOTENV_LOCKED") or "").strip() == "1"
