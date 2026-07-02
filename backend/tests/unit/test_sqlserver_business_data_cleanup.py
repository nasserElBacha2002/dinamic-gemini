"""Unit tests for shared SQL Server business cleanup helpers."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock

import pytest

from src.database.sqlserver_business_data_cleanup import (
    delete_inventory_jobs,
    run_delete_pipeline,
    validate_critical_tables_empty,
)


def test_validate_critical_tables_empty_raises_when_nonempty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "src.database.sqlserver_business_data_cleanup.collect_table_counts",
        lambda _cur: {"dbo.inventories": 3, "dbo.aisles": 0},
    )
    with pytest.raises(RuntimeError, match="non-empty"):
        validate_critical_tables_empty(object())


def test_delete_inventory_jobs_noop_when_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    cur = MagicMock()
    cur.rowcount = 0
    monkeypatch.setattr(
        "src.database.sqlserver_business_data_cleanup.count_if_exists",
        lambda *_a, **_k: 0,
    )
    delete_inventory_jobs(cur)


def test_delete_inventory_jobs_raises_when_rows_remain(monkeypatch: pytest.MonkeyPatch) -> None:
    cur = MagicMock()
    cur.rowcount = 1
    monkeypatch.setattr(
        "src.database.sqlserver_business_data_cleanup.inventory_jobs_delete_max_iterations",
        lambda: 2,
    )

    def _count_if_exists(_cur: object, schema: str, table: str) -> int:
        if table == "inventory_jobs":
            return 11
        return 0

    monkeypatch.setattr(
        "src.database.sqlserver_business_data_cleanup.count_if_exists",
        _count_if_exists,
    )
    with pytest.raises(RuntimeError, match=r"remaining=11"):
        delete_inventory_jobs(cur)


def test_run_delete_pipeline_issues_capture_null_and_deletes() -> None:
    cur = MagicMock()
    cur.fetchone.return_value = None
    run_delete_pipeline(cur)
    executed = "\n".join(str(c.args[0]) for c in cur.execute.call_args_list if c.args)
    assert "capture_session_item_id" in executed
    assert "DELETE FROM dbo.[capture_sessions]" in executed
    assert "DELETE FROM dbo.[aisle_code_scan_detections]" in executed
    assert "DELETE FROM dbo.aisle_code_scan_runs" in executed


def test_integration_cleanup_rolls_back_on_validate_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    import tests.support.sqlserver_integration_cleanup as mod

    conn = MagicMock()
    cur = MagicMock()
    cur.fetchone.return_value = None
    conn.cursor.return_value = cur
    mock_pyodbc = MagicMock()
    mock_pyodbc.connect.return_value = conn
    monkeypatch.setitem(sys.modules, "pyodbc", mock_pyodbc)

    def _boom(_cur: object) -> None:
        raise RuntimeError("verify")

    monkeypatch.setattr(mod, "validate_critical_tables_empty", _boom)

    with pytest.raises(RuntimeError, match="verify"):
        mod.cleanup_sqlserver_test_business_data("Driver={x};")
    conn.rollback.assert_called_once()
    conn.commit.assert_not_called()
