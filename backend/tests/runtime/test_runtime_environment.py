"""Tests for :mod:`src.runtime.container.runtime_environment` (Phase C5)."""

from __future__ import annotations

import pytest

from src.runtime.container.runtime_environment import is_production_like_runtime


@pytest.mark.parametrize(
    ("env_name", "env_value", "expected"),
    [
        ("APP_ENV", "production", True),
        ("APP_ENV", "PROD", True),
        ("APP_ENV", "staging", True),
        ("APP_ENV", "development", False),
        ("ENVIRONMENT", "uat", True),
        ("NODE_ENV", "production", True),
        ("NODE_ENV", "development", False),
    ],
)
def test_is_production_like_runtime(
    monkeypatch: pytest.MonkeyPatch,
    env_name: str,
    env_value: str,
    expected: bool,
) -> None:
    for k in ("APP_ENV", "ENVIRONMENT", "NODE_ENV"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv(env_name, env_value)
    assert is_production_like_runtime() is expected


def test_is_production_like_runtime_empty_vars_are_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    for k in ("APP_ENV", "ENVIRONMENT", "NODE_ENV"):
        monkeypatch.setenv(k, "  ")
    assert is_production_like_runtime() is False


def test_is_production_like_runtime_first_non_empty_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "")
    monkeypatch.setenv("ENVIRONMENT", "production")
    assert is_production_like_runtime() is True
