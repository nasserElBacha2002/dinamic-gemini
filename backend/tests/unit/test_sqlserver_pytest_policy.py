"""Unit tests for pytest SQL Server database isolation policy."""

from __future__ import annotations

import pytest

from src.env_settings.sqlserver_pytest_policy import (
    assert_pytest_sqlserver_database_is_safe,
    sqlserver_database_is_allowed_for_tests,
    sqlserver_database_looks_unsafe_for_tests,
    sqlserver_integration_auto_cleanup_enabled,
)


@pytest.fixture(autouse=True)
def _clean_sqlserver_policy_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "SQLSERVER_CONNECTION_STRING",
        "SQLSERVER_SERVER",
        "SQLSERVER_DATABASE",
        "SQLSERVER_UID",
        "SQLSERVER_PWD",
        "SQLSERVER_DRIVER",
        "DINAMIC_PYTEST_ALLOW_NON_TEST_SQLSERVER",
        "DINAMIC_PYTEST_SQLSERVER_DATABASE_ALLOWLIST",
        "DINAMIC_PYTEST_DISABLE_SQLSERVER_TEST_CLEANUP",
    ):
        monkeypatch.delenv(key, raising=False)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("dinamic_inventory_test", True),
        ("dinamic-inventory-test", True),
        ("inventory-test-db", True),
        ("test-db", True),
        ("test_inventory", True),
        ("pytest_tmp", True),
        ("prod_like", False),
        ("dinamic", False),
    ],
)
def test_sqlserver_database_is_allowed_for_tests(name: str, expected: bool) -> None:
    assert sqlserver_database_is_allowed_for_tests(name) is expected


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("dinamic_production", True),
        ("customer_prod_backup", True),
        ("staging_area", True),
        ("product_catalog_test", False),
        ("dinamic_test", False),
        ("demo_staging_only", True),
    ],
)
def test_sqlserver_database_looks_unsafe_for_tests(name: str, expected: bool) -> None:
    assert sqlserver_database_looks_unsafe_for_tests(name) is expected


def test_product_demo_uat_marked_test_allowed_before_blocklist(monkeypatch: pytest.MonkeyPatch) -> None:
    for db in ("product_catalog_test", "demo_test", "uat_test"):
        monkeypatch.setenv("SQLSERVER_DATABASE", db)
        assert_pytest_sqlserver_database_is_safe()


def test_dinamic_production_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SQLSERVER_DATABASE", "dinamic_production")
    with pytest.raises(RuntimeError, match="blocked operational"):
        assert_pytest_sqlserver_database_is_safe()


def test_customer_prod_backup_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SQLSERVER_DATABASE", "customer_prod_backup")
    with pytest.raises(RuntimeError, match="blocked operational"):
        assert_pytest_sqlserver_database_is_safe()


def test_demo_staging_only_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SQLSERVER_DATABASE", "demo_staging_only")
    with pytest.raises(RuntimeError, match="blocked operational"):
        assert_pytest_sqlserver_database_is_safe()


def test_manual_dev_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SQLSERVER_DATABASE", "dinamic_manual_dev_only")
    with pytest.raises(RuntimeError, match="does not look like"):
        assert_pytest_sqlserver_database_is_safe()


def test_assert_pytest_sqlserver_database_is_safe_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SQLSERVER_DATABASE", "dinamic_inventory_test")
    assert_pytest_sqlserver_database_is_safe()


def test_assert_pytest_respects_allowlist(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SQLSERVER_DATABASE", "exact_worktree_name")
    monkeypatch.setenv("DINAMIC_PYTEST_SQLSERVER_DATABASE_ALLOWLIST", "exact_worktree_name")
    assert_pytest_sqlserver_database_is_safe()


def test_escape_hatch_allows_non_test_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DINAMIC_PYTEST_ALLOW_NON_TEST_SQLSERVER", "1")
    monkeypatch.setenv("SQLSERVER_DATABASE", "dinamic_manual_dev_only")
    assert_pytest_sqlserver_database_is_safe()


def test_integration_cleanup_disabled_when_escape_hatch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DINAMIC_PYTEST_ALLOW_NON_TEST_SQLSERVER", "1")
    assert sqlserver_integration_auto_cleanup_enabled() is False


def test_integration_cleanup_disabled_via_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DINAMIC_PYTEST_DISABLE_SQLSERVER_TEST_CLEANUP", "1")
    assert sqlserver_integration_auto_cleanup_enabled() is False


def test_integration_cleanup_enabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DINAMIC_PYTEST_ALLOW_NON_TEST_SQLSERVER", raising=False)
    monkeypatch.delenv("DINAMIC_PYTEST_DISABLE_SQLSERVER_TEST_CLEANUP", raising=False)
    assert sqlserver_integration_auto_cleanup_enabled() is True
