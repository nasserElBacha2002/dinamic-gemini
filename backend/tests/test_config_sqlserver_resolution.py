"""SQL Server connection string resolution from split env vars."""

from __future__ import annotations

import pytest

from src.config import (
    SqlServerConfigurationError,
    load_settings,
    remap_sqlserver_connection_string_server_if_needed,
    remap_sqlserver_server_for_container_if_needed,
    resolve_sqlserver_connection_config,
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
    cfg = resolve_sqlserver_connection_config()
    assert cfg.mode == "connection_string"
    assert cfg.driver_resolution == "SQLSERVER_CONNECTION_STRING"


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
    cfg = resolve_sqlserver_connection_config()
    assert cfg.mode == "split_env"
    assert cfg.driver_resolution == "SQLSERVER_DRIVER"


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
    assert exc.value.config_mode == "incomplete_split"
    assert "config_mode=incomplete_split" in str(exc.value)


def test_no_sql_config_returns_empty_tuple(monkeypatch: pytest.MonkeyPatch) -> None:
    cs, missing = resolve_sqlserver_effective_connection_string()
    assert cs == ""
    assert missing == ()
    cfg = resolve_sqlserver_connection_config()
    assert cfg.mode == "unset"


def test_split_without_odbc_driver_env_reports_sqlserver_driver(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SQLSERVER_SERVER", "s")
    monkeypatch.setenv("SQLSERVER_DATABASE", "d")
    monkeypatch.setenv("SQLSERVER_UID", "u")
    monkeypatch.setenv("SQLSERVER_PWD", "p")
    monkeypatch.setattr("src.config._pick_odbc_driver_for_split_config", lambda _env: ("", ""))
    cs, missing = resolve_sqlserver_effective_connection_string()
    assert cs == ""
    assert missing == ("SQLSERVER_DRIVER",)


def test_require_unset_includes_config_mode_and_preflight_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(SqlServerConfigurationError) as exc:
        load_settings().require_sqlserver_connection_string()
    assert exc.value.config_mode == "unset"
    assert "config-check" in str(exc.value).lower()


def test_migration_cli_config_check_exits_3_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.database.migrations.cli import main

    assert main(["config-check"]) == 3
    assert main(["doctor"]) == 3


def test_docker_loopback_server_remapped_to_host_gateway(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("src.config._dockerenv_present", lambda: True)
    monkeypatch.delenv("SQLSERVER_DOCKER_HOST", raising=False)
    assert remap_sqlserver_server_for_container_if_needed("localhost") == "host.docker.internal"
    assert remap_sqlserver_server_for_container_if_needed("127.0.0.1,1433") == "host.docker.internal,1433"


def test_docker_loopback_respects_sqlserver_docker_host(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.config._dockerenv_present", lambda: True)
    monkeypatch.setenv("SQLSERVER_DOCKER_HOST", "172.17.0.1")
    assert remap_sqlserver_server_for_container_if_needed("localhost") == "172.17.0.1"


def test_non_docker_keeps_localhost(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.config._dockerenv_present", lambda: False)
    assert remap_sqlserver_server_for_container_if_needed("localhost") == "localhost"


def test_split_env_in_docker_remaps_server_in_connection_string(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("src.config._dockerenv_present", lambda: True)
    monkeypatch.delenv("SQLSERVER_DOCKER_HOST", raising=False)
    monkeypatch.setenv("SQLSERVER_SERVER", "localhost")
    monkeypatch.setenv("SQLSERVER_DATABASE", "db1")
    monkeypatch.setenv("SQLSERVER_UID", "u")
    monkeypatch.setenv("SQLSERVER_PWD", "p")
    monkeypatch.setenv("SQLSERVER_DRIVER", "ODBC Driver 18 for SQL Server")
    cs, missing = resolve_sqlserver_effective_connection_string()
    assert missing == ()
    assert "SERVER=host.docker.internal" in cs
    cfg = resolve_sqlserver_connection_config()
    assert cfg.sql_server_connect_target == "host.docker.internal"


def test_connection_string_mode_remapped_in_docker(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.config._dockerenv_present", lambda: True)
    monkeypatch.delenv("SQLSERVER_DOCKER_HOST", raising=False)
    raw = (
        "DRIVER={ODBC Driver 18 for SQL Server};SERVER=127.0.0.1,1433;DATABASE=db1;"
        "UID=u;PWD=p;TrustServerCertificate=yes"
    )
    monkeypatch.setenv("SQLSERVER_CONNECTION_STRING", raw)
    cfg = resolve_sqlserver_connection_config()
    assert "SERVER=host.docker.internal,1433" in cfg.connection_string
    assert cfg.sql_server_connect_target == "host.docker.internal,1433"


def test_remap_connection_string_helper_idempotent_off_docker(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.config._dockerenv_present", lambda: False)
    s = "DRIVER={x};SERVER=localhost;DATABASE=d;"
    assert remap_sqlserver_connection_string_server_if_needed(s) == s
