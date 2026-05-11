"""Isolated tests for G1 read-only drift report script guards."""

from __future__ import annotations

import pytest

from scripts.client_oriented_drift_report import _assert_select_only_sql, _g2_readiness


def test_assert_select_only_accepts_select() -> None:
    _assert_select_only_sql("SELECT 1 AS x")


def test_assert_select_only_accepts_with_cte() -> None:
    _assert_select_only_sql("WITH q AS (SELECT 1 AS n) SELECT n FROM q")


def test_assert_select_only_rejects_statement_not_beginning_with_select() -> None:
    with pytest.raises(ValueError, match="SELECT or WITH"):
        _assert_select_only_sql("INSERT INTO t VALUES (1)")


def test_assert_select_only_rejects_insert_after_select() -> None:
    with pytest.raises(ValueError, match="read-only guard"):
        _assert_select_only_sql("SELECT 1 AS x; INSERT INTO t VALUES (1)")


def test_assert_select_only_rejects_select_with_subquery_insert() -> None:
    with pytest.raises(ValueError, match="read-only guard"):
        _assert_select_only_sql("SELECT 1; INSERT INTO t VALUES (1)")


def test_g2_readiness_without_db_is_observations() -> None:
    r = {"db_connected": False, "inventory_client_drift": {}}
    assert _g2_readiness(r) == "READY_FOR_G2_WITH_OBSERVATIONS"


def test_g2_readiness_orphan_not_ready() -> None:
    r = {
        "db_connected": True,
        "meta": {"recent_days_window": 30},
        "inventory_client_drift": {"client_id_orphan_missing_client_row": 1},
    }
    assert _g2_readiness(r) == "NOT_READY_FOR_G2"


def test_g2_readiness_recent_null_observations() -> None:
    r = {
        "db_connected": True,
        "meta": {"recent_days_window": 7},
        "inventory_client_drift": {
            "client_id_orphan_missing_client_row": 0,
            "client_id_null_created_last_7_days": 3,
        },
    }
    assert _g2_readiness(r) == "READY_FOR_G2_WITH_OBSERVATIONS"


def test_g2_readiness_clean_ready() -> None:
    r = {
        "db_connected": True,
        "meta": {"recent_days_window": 30},
        "inventory_client_drift": {
            "client_id_orphan_missing_client_row": 0,
            "client_id_null_created_last_30_days": 0,
            "client_id_null": 0,
        },
    }
    assert _g2_readiness(r) == "READY_FOR_G2"
