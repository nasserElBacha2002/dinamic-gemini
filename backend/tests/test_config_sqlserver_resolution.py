"""SQL Server connection string resolution from split env vars."""

from __future__ import annotations

import pytest

from src.config import (
    SqlServerConfigurationError,
    load_settings,
    resolve_sqlserver_effective_connection_string,
)


@pytest.fixture(autouse=True)
def _clean_sql_env(monkeypatch: pytest.MonkeyPatch):
    for key in (
        "SQLSERVER_CONNECTION_STRING",
        "SQLSERVER_SERVER",
        "SQLSERVER_DATABASE",
        "SQLSERVER_UID",
        "SQLSERVER_PWD",
        "SQLSERVER_DRIVER",
    ):
        monkeypatch.delenv(key, raising=False)
    yield


def test_explicit_connection_string_takes_precedence(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SQLSERVER_CONNECTION_STRING", " DRIVER=explicit; ")
    monkeypatch.setenv("SQLSERVER_SERVER", "should-not-see")
    cs, missing = resolve_sqlserver_effective_connection_string()
    assert cs == "DRIVER=explicit;"
    assert missing == ()


def test_split_vars_stripped_and_built(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SQLSERVER_SERVER", " localhost ")
    monkeypatch.setenv("SQLSERVER_DATABASE", " db1 ")
    monkeypatch.setenv("SQLSERVER_UID", " u ")
    monkeypatch.setenv("SQLSERVER_PWD", " p ")
    monkeypatch.setenv("SQLSERVER_DRIVER", " ODBC Driver 18 for SQL Server ")
    cs, missing = resolve_sqlserver_effective_connection_string()
    assert missing == ()
    assert "SERVER=localhost" in cs
    assert "DATABASE=db1" in cs
    assert "UID=u" in cs
    assert "PWD=p" in cs
    assert "DRIVER={ODBC Driver 18 for SQL Server}" in cs


def test_partial_split_reports_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SQLSERVER_SERVER", "s")
    cs, missing = resolve_sqlserver_effective_connection_string()
    assert cs == ""
    assert "SQLSERVER_DATABASE" in missing
    assert "SQLSERVER_UID" in missing
    assert "SQLSERVER_PWD" in missing


def test_require_raises_with_missing_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SQLSERVER_SERVER", "only-server")
    with pytest.raises(SqlServerConfigurationError) as exc:
        load_settings().require_sqlserver_connection_string()
    assert exc.value.missing_env_vars


def test_no_sql_config_returns_empty_tuple(monkeypatch: pytest.MonkeyPatch) -> None:
    cs, missing = resolve_sqlserver_effective_connection_string()
    assert cs == ""
    assert missing == ()


def test_split_without_odbc_driver_env_reports_sqlserver_driver(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SQLSERVER_SERVER", "s")
    monkeypatch.setenv("SQLSERVER_DATABASE", "d")
    monkeypatch.setenv("SQLSERVER_UID", "u")
    monkeypatch.setenv("SQLSERVER_PWD", "p")
    monkeypatch.setattr("src.config._get_available_sqlserver_driver", lambda: "")
    cs, missing = resolve_sqlserver_effective_connection_string()
    assert cs == ""
    assert missing == ("SQLSERVER_DRIVER",)
