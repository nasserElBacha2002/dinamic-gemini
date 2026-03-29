"""Unit tests for scripts/check_migration_presence.py path/DDL heuristics."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import patch

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _load_script():
    script_path = _BACKEND_ROOT / "scripts" / "check_migration_presence.py"
    spec = importlib.util.spec_from_file_location("check_migration_presence_mod", script_path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cm = _load_script()


@pytest.mark.parametrize(
    "snippet,expect",
    [
        ("+    CREATE TABLE foo (id TEXT)", True),
        ("-    ALTER TABLE foo ADD COLUMN bar INT", True),
        ("+  drop table foo", True),
        ("+    create unique index ix_foo ON foo (a)", True),
        ("+    DROP INDEX ix_foo", True),
        ("+    ADD COLUMN qty INT", True),
        ("+    DROP COLUMN legacy", True),
        ("+    cursor.execute('SELECT * FROM foo')", False),
        ("+    UPDATE foo SET x = 1", False),
        ("+    INSERT INTO foo VALUES (1)", False),
        ("+    # refactor: clearer variable names only", False),
        ("", False),
    ],
)
def test_diff_text_looks_schema_affecting(snippet: str, expect: bool) -> None:
    diff = f"diff --git a/x b/x\n@@\n{snippet}\n"
    assert cm._diff_text_looks_schema_affecting(diff) is expect


def test_is_memory_repository_path() -> None:
    assert cm._is_memory_repository_path(
        "backend/src/infrastructure/repositories/memory_position_repository.py"
    )
    assert not cm._is_memory_repository_path(
        "backend/src/infrastructure/repositories/sql_position_repository.py"
    )


def test_is_sql_repository_path() -> None:
    assert cm._is_sql_repository_path(
        "backend/src/infrastructure/repositories/sql_position_repository.py"
    )
    assert not cm._is_sql_repository_path(
        "backend/src/infrastructure/repositories/memory_position_repository.py"
    )


def test_path_requires_migration_review_schema_sql() -> None:
    assert cm._path_requires_migration_review(
        "backend/src/database/schema.sql",
        "main",
        "HEAD",
    )


def test_path_requires_migration_memory_repo_returns_false() -> None:
    assert not cm._path_requires_migration_review(
        "backend/src/infrastructure/repositories/memory_position_repository.py",
        "main",
        "HEAD",
    )


@patch.object(cm, "_git_diff_for_path", return_value="+CREATE TABLE x (id TEXT)\n")
def test_path_requires_sql_repo_when_diff_has_ddl(_mock_diff: object) -> None:
    assert cm._path_requires_migration_review(
        "backend/src/infrastructure/repositories/sql_position_repository.py",
        "main",
        "HEAD",
    )


@patch.object(cm, "_git_diff_for_path", return_value="+    SELECT id FROM positions\n")
def test_path_requires_sql_repo_when_diff_has_only_select(_mock_diff: object) -> None:
    assert not cm._path_requires_migration_review(
        "backend/src/infrastructure/repositories/sql_position_repository.py",
        "main",
        "HEAD",
    )
