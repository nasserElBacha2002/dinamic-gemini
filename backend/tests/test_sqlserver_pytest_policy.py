"""Unit tests for pytest SQL Server database isolation policy."""

from __future__ import annotations

import pytest

from src.env_settings.sqlserver_pytest_policy import (
    assert_pytest_sqlserver_database_is_safe,
    sqlserver_database_is_allowed_for_tests,
    sqlserver_database_looks_unsafe_for_tests,
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
    ):
        monkeypatch.delenv(key, raising=False)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("dinamic_inventory_test", True),
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
        ("dinamic_test", False),
    ],
)
def test_sqlserver_database_looks_unsafe_for_tests(name: str, expected: bool) -> None:
    assert sqlserver_database_looks_unsafe_for_tests(name) is expected


def test_assert_pytest_sqlserver_database_is_safe_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SQLSERVER_DATABASE", "dinamic_inventory_test")
    assert_pytest_sqlserver_database_is_safe()


def test_assert_pytest_sqlserver_database_is_safe_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SQLSERVER_DATABASE", "dinamic_manual_dev_only")
    with pytest.raises(RuntimeError):
        assert_pytest_sqlserver_database_is_safe()


def test_assert_pytest_respects_allowlist(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SQLSERVER_DATABASE", "exact_worktree_name")
    monkeypatch.setenv("DINAMIC_PYTEST_SQLSERVER_DATABASE_ALLOWLIST", "exact_worktree_name")
    assert_pytest_sqlserver_database_is_safe()
