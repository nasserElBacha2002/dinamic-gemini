"""Phase 14.1 — legacy Stage-8 SQL soft freeze (writes + optional bridge disable)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

import src.config as config_module
from src.database.repository import JobEventsRepository, JobsRepository, PalletResultsRepository
from src.jobs import job_store
from src.legacy.persistence_observability import (
    reset_legacy_sql_bridge_bypassed_flag_for_tests,
    reset_legacy_sql_repositories_materialization_flag,
)


@dataclass
class _FakeCursor:
    row: Any | None = None
    execute_calls: int = 0
    last_query: str = ""

    def execute(self, query: str, params: tuple[Any, ...] = ()) -> None:
        self.execute_calls += 1
        self.last_query = query

    def fetchone(self):
        return self.row

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None


class _FakeClient:
    def __init__(self, row: Any | None = None) -> None:
        self._cursor = _FakeCursor(row=row)

    def cursor(self):
        return self._cursor


class _Row:
    """Minimal row for get_job SELECT mapping (see test_jobs_repository_storage_metadata)."""

    id = "job-1"
    created_at = None
    updated_at = None
    status = "queued"
    mode = "hybrid"
    confidence_threshold = 0.7
    video_path = ""
    metadata = None
    progress_stage = ""
    progress_percent = 0
    error_code = None
    error_message = None
    report_json_path = None
    report_csv_path = None
    artifacts_dir = None
    report_storage_provider = None
    report_storage_bucket = None
    report_json_storage_key = None
    report_csv_storage_key = None
    report_content_type = None
    report_file_size_bytes = None
    report_etag = None
    log_storage_provider = None
    log_storage_bucket = None
    execution_log_storage_key = None
    execution_log_content_type = None
    execution_log_file_size_bytes = None
    execution_log_etag = None
    input_type = "video"
    input_manifest_path = None
    photos_dir = None


@pytest.fixture(autouse=True)
def _reset_config_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate env-based Settings between tests."""
    yield
    monkeypatch.delenv("LEGACY_STAGE8_SQL_WRITES_DISABLED", raising=False)
    monkeypatch.delenv("LEGACY_STAGE8_SQL_BRIDGE_DISABLED", raising=False)
    config_module._settings = None
    reset_legacy_sql_repositories_materialization_flag()
    reset_legacy_sql_bridge_bypassed_flag_for_tests()


def test_create_job_executes_sql_when_writes_not_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LEGACY_STAGE8_SQL_WRITES_DISABLED", raising=False)
    config_module._settings = None
    client = _FakeClient()
    repo = JobsRepository(client)
    repo.create_job(
        job_id="j1",
        video_path="",
        mode="hybrid",
        confidence_threshold=0.7,
        engine_version="v2.0",
    )
    assert client._cursor.execute_calls >= 1
    assert "INSERT INTO jobs" in client._cursor.last_query


def test_create_job_skips_sql_when_writes_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LEGACY_STAGE8_SQL_WRITES_DISABLED", "true")
    config_module._settings = None
    client = _FakeClient()
    repo = JobsRepository(client)
    repo.create_job(
        job_id="j1",
        video_path="",
        mode="hybrid",
        confidence_threshold=0.7,
        engine_version="v2.0",
    )
    assert client._cursor.execute_calls == 0


def test_get_job_still_queries_when_writes_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LEGACY_STAGE8_SQL_WRITES_DISABLED", "true")
    config_module._settings = None
    client = _FakeClient(row=_Row())
    repo = JobsRepository(client)
    data = repo.get_job("job-1")
    assert data is not None
    assert client._cursor.execute_calls >= 1


def test_claim_next_queued_job_returns_none_when_writes_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LEGACY_STAGE8_SQL_WRITES_DISABLED", "true")
    config_module._settings = None
    client = _FakeClient()
    repo = JobsRepository(client)
    assert repo.claim_next_queued_job() is None
    assert client._cursor.execute_calls == 0


def test_insert_pallet_results_skipped_when_writes_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LEGACY_STAGE8_SQL_WRITES_DISABLED", "true")
    config_module._settings = None
    client = _FakeClient()
    repo = PalletResultsRepository(client)
    repo.insert_pallet_results("job-1", [{"pallet_id": "p1", "source": "gemini"}])
    assert client._cursor.execute_calls == 0


def test_insert_event_skipped_when_writes_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LEGACY_STAGE8_SQL_WRITES_DISABLED", "true")
    config_module._settings = None
    client = _FakeClient()
    repo = JobEventsRepository(client)
    repo.insert_event("job-1", "TEST", {})
    assert client._cursor.execute_calls == 0


@dataclass
class _SettingsBridgeOff:
    sqlserver_enabled: bool = True
    sqlserver_effective_connection_string: str = "Driver={ODBC Driver 18 for SQL Server};Server=x;"

    legacy_stage8_sql_bridge_disabled: bool = True
    legacy_stage8_sql_writes_disabled: bool = False

    def require_sqlserver_connection_string(self) -> str:
        return "Driver={ODBC Driver 18 for SQL Server};Server=x;"


def test_db_repos_returns_none_when_bridge_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    reset_legacy_sql_repositories_materialization_flag()
    reset_legacy_sql_bridge_bypassed_flag_for_tests()
    monkeypatch.setattr(job_store, "load_settings", lambda: _SettingsBridgeOff())
    assert job_store._db_repos() is None
