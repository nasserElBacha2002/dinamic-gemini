"""Unit tests for legacy SQL observability helpers (Stage 1)."""

from __future__ import annotations

from src.legacy.persistence_observability import classify_stage8_access_path_kind


def test_classify_legacy_jobs_module() -> None:
    assert classify_stage8_access_path_kind("src.jobs.job_store") == "legacy_jobs"


def test_classify_v3_api_module() -> None:
    assert classify_stage8_access_path_kind("src.api.routes.v3.positions") == "v3_api"


def test_classify_v3_application_module() -> None:
    assert classify_stage8_access_path_kind("src.application.use_cases.list_aisle_positions") == "v3_application"


def test_classify_unknown_module() -> None:
    assert classify_stage8_access_path_kind(None) == "unknown"
