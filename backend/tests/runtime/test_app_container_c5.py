"""Phase C5 — production fallback policy, lifecycle, reset/close wiring."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

import src.config as config_module
from src.config import load_settings
from src.runtime.app_container import AppContainer, get_app_container, reset_app_container_for_tests
from src.runtime.container.repository_backend import RepositoryBackendMode


def test_explicit_v3_allow_true_overrides_production_on_probe_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SQLSERVER_ENABLED", "true")
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("V3_ALLOW_IN_MEMORY_FALLBACK", "true")
    monkeypatch.setenv(
        "SQLSERVER_CONNECTION_STRING",
        "Driver=ODBC Driver 18 for SQL Server;Server=127.0.0.1,1;Database=x;Uid=x;Pwd=x;"
        "TrustServerCertificate=yes",
    )
    config_module._settings = None

    class _FailingCursor:
        def __enter__(self) -> None:
            raise ConnectionError("simulated probe failure")

        def __exit__(self, *_a: object) -> bool:
            return False

    class _ProbeFailClient:
        def __init__(self, *_a: object, **_k: object) -> None:
            pass

        def cursor(self) -> _FailingCursor:
            return _FailingCursor()

    monkeypatch.setattr("src.runtime.app_container.SqlServerClient", _ProbeFailClient)
    c = AppContainer(load_settings())
    res = c._get_repository_backend_resolution()
    assert res.mode == RepositoryBackendMode.MEMORY_FALLBACK


def test_explicit_v3_allow_false_disables_fallback_in_non_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SQLSERVER_ENABLED", "true")
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("V3_ALLOW_IN_MEMORY_FALLBACK", "false")
    monkeypatch.setenv(
        "SQLSERVER_CONNECTION_STRING",
        "Driver=ODBC Driver 18 for SQL Server;Server=127.0.0.1,1;Database=x;Uid=x;Pwd=x;"
        "TrustServerCertificate=yes",
    )
    config_module._settings = None

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


def test_unset_v3_allow_in_production_disallows_memory_fallback_on_probe_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SQLSERVER_ENABLED", "true")
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("V3_ALLOW_IN_MEMORY_FALLBACK", raising=False)
    monkeypatch.setenv(
        "SQLSERVER_CONNECTION_STRING",
        "Driver=ODBC Driver 18 for SQL Server;Server=127.0.0.1,1;Database=x;Uid=x;Pwd=x;"
        "TrustServerCertificate=yes",
    )
    config_module._settings = None

    class _FailingCursor:
        def __enter__(self) -> None:
            raise RuntimeError("simulated SQL unreachable")

        def __exit__(self, *_a: object) -> bool:
            return False

    class _ProbeFailClient:
        def __init__(self, *_a: object, **_k: object) -> None:
            pass

        def cursor(self) -> _FailingCursor:
            return _FailingCursor()

    monkeypatch.setattr("src.runtime.app_container.SqlServerClient", _ProbeFailClient)
    c = AppContainer(load_settings())
    with pytest.raises(RuntimeError, match="simulated SQL unreachable"):
        c._get_repository_backend_resolution()
    assert c._repository_backend_resolution is None


def test_unset_v3_allow_in_local_runtime_allows_memory_fallback_on_probe_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SQLSERVER_ENABLED", "true")
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("NODE_ENV", raising=False)
    monkeypatch.delenv("V3_ALLOW_IN_MEMORY_FALLBACK", raising=False)
    monkeypatch.setenv(
        "SQLSERVER_CONNECTION_STRING",
        "Driver=ODBC Driver 18 for SQL Server;Server=127.0.0.1,1;Database=x;Uid=x;Pwd=x;"
        "TrustServerCertificate=yes",
    )
    config_module._settings = None

    class _FailingCursor:
        def __enter__(self) -> None:
            raise ConnectionError("simulated probe failure")

        def __exit__(self, *_a: object) -> bool:
            return False

    class _ProbeFailClient:
        def __init__(self, *_a: object, **_k: object) -> None:
            pass

        def cursor(self) -> _FailingCursor:
            return _FailingCursor()

    monkeypatch.setattr("src.runtime.app_container.SqlServerClient", _ProbeFailClient)
    c = AppContainer(load_settings())
    res = c._get_repository_backend_resolution()
    assert res.mode == RepositoryBackendMode.MEMORY_FALLBACK


def test_app_container_close_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SQLSERVER_ENABLED", "false")
    config_module._settings = None
    c = AppContainer(load_settings())
    c.get_inventory_repo()
    c.close()
    c.close()


def test_app_container_close_does_not_construct_sql_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SQLSERVER_ENABLED", "false")
    config_module._settings = None
    from unittest.mock import patch

    with patch("src.runtime.app_container.SqlServerClient") as mock_sql:
        c = AppContainer(load_settings())
        c.close()
        mock_sql.assert_not_called()


def test_reset_app_container_for_tests_invokes_close(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SQLSERVER_ENABLED", "false")
    config_module._settings = None
    reset_app_container_for_tests()
    recorded: list[str] = []
    orig_close = AppContainer.close

    def _wrap_close(self: AppContainer) -> None:
        recorded.append("close")
        return orig_close(self)

    monkeypatch.setattr(AppContainer, "close", _wrap_close)
    _ = get_app_container()
    reset_app_container_for_tests()
    assert recorded == ["close"]


def test_app_container_close_calls_resource_shutdown_when_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SQLSERVER_ENABLED", "false")
    config_module._settings = None
    c = AppContainer(load_settings())
    svc = MagicMock(spec=["shutdown"])
    c._worker_launch_service = svc
    c.close()
    svc.shutdown.assert_called_once()
