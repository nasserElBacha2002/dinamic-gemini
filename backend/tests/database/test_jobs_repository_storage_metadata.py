from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.database.repository import JobsRepository


@dataclass
class _FakeCursor:
    row: Any | None
    last_query: str = ""
    last_params: tuple[Any, ...] = ()

    def execute(self, query: str, params: tuple[Any, ...]) -> None:
        self.last_query = query
        self.last_params = params

    def fetchone(self):
        return self.row

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None


class _FakeClient:
    def __init__(self, row: Any | None) -> None:
        self._cursor = _FakeCursor(row=row)

    def cursor(self):
        return self._cursor


class _Row:
    id = "job-1"
    created_at = None
    updated_at = None
    status = "succeeded"
    mode = "hybrid"
    confidence_threshold = 0.7
    video_path = ""
    metadata = None
    progress_stage = "done"
    progress_percent = 100
    error_code = None
    error_message = None
    report_json_path = "legacy/report.json"
    report_csv_path = "legacy/report.csv"
    artifacts_dir = "legacy/job-dir"
    report_storage_provider = "s3"
    report_storage_bucket = "bucket-a"
    report_json_storage_key = "jobs/job-1/report.json"
    report_csv_storage_key = "jobs/job-1/report.csv"
    report_content_type = "application/json"
    report_file_size_bytes = 500
    report_etag = "etag-report"
    log_storage_provider = "s3"
    log_storage_bucket = "bucket-a"
    execution_log_storage_key = "jobs/job-1/execution_log.jsonl"
    execution_log_content_type = "application/x-ndjson"
    execution_log_file_size_bytes = 123
    execution_log_etag = "etag-log"
    input_type = "photos"
    input_manifest_path = "input_manifest.json"
    photos_dir = "input_photos"


def test_jobs_repository_get_job_returns_provider_aware_output_fields() -> None:
    repo = JobsRepository(_FakeClient(_Row()))
    job = repo.get_job("job-1")
    assert job is not None
    output = job["output"]
    assert output is not None
    assert output["report_storage_provider"] == "s3"
    assert output["report_storage_bucket"] == "bucket-a"
    assert output["report_json_storage_key"] == "jobs/job-1/report.json"
    assert output["execution_log_storage_key"] == "jobs/job-1/execution_log.jsonl"


class _LegacyOnlyRow(_Row):
    report_storage_provider = None
    report_storage_bucket = None
    report_json_storage_key = None
    report_csv_storage_key = None
    log_storage_provider = None
    log_storage_bucket = None
    execution_log_storage_key = None


def test_jobs_repository_get_job_falls_back_to_legacy_paths_when_provider_fields_missing() -> None:
    repo = JobsRepository(_FakeClient(_LegacyOnlyRow()))
    job = repo.get_job("job-1")
    assert job is not None
    output = job["output"]
    assert output is not None
    assert output["report_json_path"] == "legacy/report.json"
    assert output["report_json_storage_key"] == "legacy/report.json"
    assert output["report_csv_storage_key"] == "legacy/report.csv"
