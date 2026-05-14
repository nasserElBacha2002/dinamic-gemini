"""Composition root: container creation and parity with v3_deps entrypoints."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import pytest

import src.config as config_module
from src.api import dependencies as deps
from src.config import AppSettings, Settings, load_settings
from src.infrastructure.repositories.memory_inventory_repository import MemoryInventoryRepository
from src.infrastructure.repositories.memory_job_repository import MemoryJobRepository
from src.runtime.app_container import AppContainer, get_app_container, reset_app_container_for_tests
from src.runtime.container.repository_backend import (
    RepositoryBackendMode,
    RepositoryBackendResolution,
)
from src.runtime.v3_deps import get_aisle_repo, get_artifact_store, get_inventory_repo, get_job_repo


@pytest.fixture(autouse=True)
def _reset_container_and_settings(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SQLSERVER_ENABLED", "false")
    reset_app_container_for_tests()
    config_module._settings = None
    yield
    reset_app_container_for_tests()
    config_module._settings = None


def test_app_settings_is_settings_alias() -> None:
    assert Settings is AppSettings


def test_container_builds_from_explicit_settings() -> None:
    s = AppSettings()
    c = AppContainer(s)
    assert c.settings is s
    inv = c.get_inventory_repo()
    assert inv is c.get_inventory_repo()


def test_settings_groups_env_database_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SQLSERVER_ENABLED", "false")
    config_module._settings = None
    reset_app_container_for_tests()
    s = load_settings()
    assert s.sqlserver_enabled is False


def test_artifact_storage_single_instance_across_api_v3deps_container(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """API ``get_artifact_storage``, ``v3_deps.get_artifact_store``, and the container must share one adapter."""
    out = str(tmp_path / "artifact_wiring_out")
    monkeypatch.setenv("ARTIFACT_STORAGE_PROVIDER", "local")
    monkeypatch.setenv("OUTPUT_DIR", out)
    config_module._settings = None
    reset_app_container_for_tests()

    c = get_app_container()
    a = deps.get_artifact_storage()
    b = c.get_artifact_storage()
    d = get_artifact_store()
    assert a is b is d


def test_v3_deps_repo_getters_delegate_to_same_container_instances() -> None:
    c = get_app_container()
    assert get_inventory_repo() is c.get_inventory_repo()
    assert get_job_repo() is c.get_job_repo()
    assert get_aisle_repo() is c.get_aisle_repo()


def test_repository_backend_resolution_is_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SQLSERVER_ENABLED", "false")
    config_module._settings = None
    reset_app_container_for_tests()
    c = AppContainer(load_settings())
    r1 = c._get_repository_backend_resolution()
    r2 = c._get_repository_backend_resolution()
    assert r1 is r2
    assert r1.mode == RepositoryBackendMode.MEMORY_ONLY


def test_sqlserver_client_not_instantiated_when_sql_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SQLSERVER_ENABLED", "false")
    config_module._settings = None
    reset_app_container_for_tests()
    with patch("src.runtime.app_container.SqlServerClient") as mock_sql:
        c = AppContainer(load_settings())
        c._get_repository_backend_resolution()
        c._get_repository_backend_resolution()
        c.get_inventory_repo()
        mock_sql.assert_not_called()


def test_single_sql_client_construct_when_sql_enabled_two_repos(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SQLSERVER_ENABLED", "true")
    monkeypatch.setenv(
        "SQLSERVER_CONNECTION_STRING",
        "Driver=ODBC Driver 18 for SQL Server;Server=127.0.0.1,1;Database=x;Uid=x;Pwd=x;"
        "TrustServerCertificate=yes",
    )
    config_module._settings = None
    reset_app_container_for_tests()

    constructs = {"n": 0}

    class _FakeSqlClient:
        def __init__(self, *_a: object, **_k: object) -> None:
            constructs["n"] += 1

        @contextmanager
        def cursor(self):
            class _Cur:
                def execute(self, *_a: object, **_k: object) -> None:
                    return None

            yield _Cur()

    monkeypatch.setattr("src.runtime.app_container.SqlServerClient", _FakeSqlClient)
    c = AppContainer(load_settings())
    c.get_inventory_repo()
    c.get_job_repo()
    assert constructs["n"] == 1


def test_memory_fallback_cached_single_sql_probe_two_memory_repos(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Probe fails once → MEMORY_FALLBACK; later repos stay memory without constructing SqlServerClient again."""
    monkeypatch.setenv("SQLSERVER_ENABLED", "true")
    monkeypatch.setenv("V3_ALLOW_IN_MEMORY_FALLBACK", "true")
    monkeypatch.setenv(
        "SQLSERVER_CONNECTION_STRING",
        "Driver=ODBC Driver 18 for SQL Server;Server=127.0.0.1,1;Database=x;Uid=x;Pwd=x;"
        "TrustServerCertificate=yes",
    )
    config_module._settings = None
    reset_app_container_for_tests()

    constructs = {"n": 0}

    class _FailingCursor:
        def __enter__(self) -> None:
            raise ConnectionError("simulated probe failure")

        def __exit__(self, *_a: object) -> bool:
            return False

    class _ProbeFailClient:
        def __init__(self, *_a: object, **_k: object) -> None:
            constructs["n"] += 1

        def cursor(self) -> _FailingCursor:
            return _FailingCursor()

    monkeypatch.setattr("src.runtime.app_container.SqlServerClient", _ProbeFailClient)
    c = AppContainer(load_settings())
    assert c._get_repository_backend_resolution().mode == RepositoryBackendMode.MEMORY_FALLBACK
    inv = c.get_inventory_repo()
    job = c.get_job_repo()
    assert isinstance(inv, MemoryInventoryRepository)
    assert isinstance(job, MemoryJobRepository)
    assert constructs["n"] == 1


def test_sql_mode_build_sql_failure_does_not_fallback_to_memory() -> None:
    c = AppContainer(load_settings())
    c._repository_backend_resolution = RepositoryBackendResolution(
        mode=RepositoryBackendMode.SQL,
        sql_enabled=True,
        fallback_allowed=True,
    )
    c._v3_sql_client = object()  # type: ignore[assignment]

    memory_called = False

    def build_sql(_client: object) -> str:
        raise RuntimeError("sql repo constructor failed")

    def build_memory() -> str:
        nonlocal memory_called
        memory_called = True
        return "mem"

    with pytest.raises(RuntimeError, match="sql repo constructor failed"):
        c._build_sql_repository_or_memory(
            backend_info_name="TestRepo",
            sql_error_subject="test_repo",
            build_sql=build_sql,
            build_memory=build_memory,
        )
    assert memory_called is False


def test_build_sql_repository_memory_only_uses_memory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SQLSERVER_ENABLED", "false")
    config_module._settings = None
    reset_app_container_for_tests()
    c = AppContainer(load_settings())
    sql_ran: list[int] = []

    def build_sql(_client: object) -> str:
        sql_ran.append(1)
        raise AssertionError("build_sql must not run")

    def build_memory() -> str:
        return "mem"

    assert (
        c._build_sql_repository_or_memory(
            backend_info_name="x",
            sql_error_subject="x",
            build_sql=build_sql,
            build_memory=build_memory,
        )
        == "mem"
    )
    assert sql_ran == []


def test_build_sql_repository_memory_fallback_uses_memory(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SQLSERVER_ENABLED", "false")
    config_module._settings = None
    reset_app_container_for_tests()
    c = AppContainer(load_settings())
    c._repository_backend_resolution = RepositoryBackendResolution(
        mode=RepositoryBackendMode.MEMORY_FALLBACK,
        sql_enabled=True,
        fallback_allowed=True,
        reason="prior probe",
    )
    sql_ran: list[int] = []

    def build_sql(_client: object) -> str:
        sql_ran.append(1)
        raise AssertionError("build_sql must not run")

    def build_memory() -> str:
        return "mf"

    assert (
        c._build_sql_repository_or_memory(
            backend_info_name="x",
            sql_error_subject="x",
            build_sql=build_sql,
            build_memory=build_memory,
        )
        == "mf"
    )
    assert sql_ran == []


def test_build_sql_repository_sql_mode_calls_build_sql(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SQLSERVER_ENABLED", "false")
    config_module._settings = None
    reset_app_container_for_tests()
    c = AppContainer(load_settings())
    c._repository_backend_resolution = RepositoryBackendResolution(
        mode=RepositoryBackendMode.SQL,
        sql_enabled=True,
        fallback_allowed=False,
    )
    sentinel = object()
    c._v3_sql_client = sentinel  # type: ignore[assignment]
    mem_ran: list[int] = []

    def build_sql(client: object) -> object:
        assert client is sentinel
        return "sql_repo"

    def build_memory() -> str:
        mem_ran.append(1)
        raise AssertionError("memory must not run")

    assert (
        c._build_sql_repository_or_memory(
            backend_info_name="x",
            sql_error_subject="x",
            build_sql=build_sql,
            build_memory=build_memory,
        )
        == "sql_repo"
    )
    assert mem_ran == []


def test_get_aisle_repo_returns_cached_singleton(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SQLSERVER_ENABLED", "false")
    config_module._settings = None
    reset_app_container_for_tests()
    c = AppContainer(load_settings())
    a1 = c.get_aisle_repo()
    a2 = c.get_aisle_repo()
    assert a1 is a2


def test_get_job_repo_returns_cached_singleton(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SQLSERVER_ENABLED", "false")
    config_module._settings = None
    reset_app_container_for_tests()
    c = AppContainer(load_settings())
    j1 = c.get_job_repo()
    j2 = c.get_job_repo()
    assert j1 is j2


def test_repository_backend_resolution_raises_when_probe_fails_and_fallback_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SQLSERVER_ENABLED", "true")
    monkeypatch.setenv("V3_ALLOW_IN_MEMORY_FALLBACK", "false")
    monkeypatch.setenv(
        "SQLSERVER_CONNECTION_STRING",
        "Driver=ODBC Driver 18 for SQL Server;Server=127.0.0.1,1;Database=x;Uid=x;Pwd=x;"
        "TrustServerCertificate=yes",
    )
    config_module._settings = None
    reset_app_container_for_tests()

    class _FailingCursor:
        def __enter__(self) -> None:
            raise OSError("simulated probe failure")

        def __exit__(self, *_a: object) -> bool:
            return False

    class _ProbeFailClient:
        def __init__(self, *_a: object, **_k: object) -> None:
            pass

        def cursor(self) -> _FailingCursor:
            return _FailingCursor()

    monkeypatch.setattr("src.runtime.app_container.SqlServerClient", _ProbeFailClient)
    c = AppContainer(load_settings())
    with pytest.raises(OSError, match="simulated probe failure"):
        c._get_repository_backend_resolution()
    assert c._repository_backend_resolution is None
