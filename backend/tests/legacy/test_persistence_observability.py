"""Unit tests for legacy SQL observability helpers (Stage 1)."""

from __future__ import annotations

import logging

import pytest

from src.legacy.persistence_observability import (
    classify_stage8_access_path_kind,
    log_legacy_sql_repositories_materialized_once_per_process,
    reset_legacy_sql_bridge_bypassed_flag_for_tests,
    reset_legacy_sql_repositories_materialization_flag,
)


def test_classify_legacy_jobs_module() -> None:
    assert classify_stage8_access_path_kind("src.jobs.job_store") == "legacy_jobs"


def test_classify_v3_api_module() -> None:
    assert classify_stage8_access_path_kind("src.api.routes.v3.positions") == "v3_api"


def test_classify_v3_application_module() -> None:
    assert (
        classify_stage8_access_path_kind("src.application.use_cases.list_aisle_positions")
        == "v3_application"
    )


def test_classify_unknown_module() -> None:
    assert classify_stage8_access_path_kind(None) == "unknown"


def test_legacy_sql_repositories_materialized_logs_once_per_process(
    caplog: pytest.LogCaptureFixture,
) -> None:
    reset_legacy_sql_repositories_materialization_flag()
    reset_legacy_sql_bridge_bypassed_flag_for_tests()
    caplog.set_level(logging.INFO, logger="dinamic.legacy_sql")
    log_legacy_sql_repositories_materialized_once_per_process(source="test")
    log_legacy_sql_repositories_materialized_once_per_process(source="test_again")
    materialized = [
        r
        for r in caplog.records
        if r.name == "dinamic.legacy_sql"
        and "legacy_sql_repositories_materialized_once_per_process" in r.getMessage()
    ]
    assert len(materialized) == 1
    assert "source=test" in materialized[0].getMessage()
    reset_legacy_sql_repositories_materialization_flag()
    reset_legacy_sql_bridge_bypassed_flag_for_tests()
