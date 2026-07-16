"""SqlJobRepository.list_jobs_for_targets — shape, batching, and no run-cap."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from src.application.services.billable_job_cost_aggregation import (
    billable_cost_for_job,
    sum_billable_costs_by_aisle_id,
)
from src.domain.jobs.entities import Job, JobStatus
from src.infrastructure.repositories.memory_job_repository import MemoryJobRepository
from src.infrastructure.repositories.sql_job_repository import (
    TARGET_ID_BATCH_SIZE,
    SqlJobRepository,
)

NOW = datetime(2026, 3, 15, 12, 0, 0, tzinfo=timezone.utc)


def _cost_snapshot(total: str, status: str = "exact") -> dict:
    return {
        "llm_cost_snapshot": {
            "provider": "gemini",
            "model": "gemini-2.0",
            "usage": {
                "input_tokens": 10,
                "output_tokens": 5,
                "cached_input_tokens": 0,
                "cache_write_tokens": 0,
                "thinking_tokens": 0,
                "tool_request_count": 0,
                "image_input_count": 0,
                "audio_input_tokens": 0,
                "video_input_tokens": 0,
            },
            "pricing_snapshot": {"billing_currency": "USD"},
            "computed_cost": {"total_cost": total, "currency": "USD"},
            "capture_status": status,
            "capture_notes": [],
        }
    }


def _job(
    job_id: str,
    aisle_id: str,
    *,
    cost: str | None = "1",
    status: JobStatus = JobStatus.SUCCEEDED,
    job_type: str = "process_aisle",
    target_type: str = "aisle",
    offset_sec: int = 0,
) -> Job:
    created = NOW + timedelta(seconds=offset_sec)
    return Job(
        id=job_id,
        target_type=target_type,
        target_id=aisle_id,
        job_type=job_type,
        status=status,
        payload_json={},
        created_at=created,
        updated_at=created,
        finished_at=created,
        result_json=_cost_snapshot(cost) if cost is not None else None,
    )


class _RecordingCursor:
    def __init__(self, rows_per_execute: list[list[Any]] | None = None) -> None:
        self.executions: list[tuple[str, tuple | list]] = []
        self._rows = list(rows_per_execute or [])
        self.rowcount = 0

    def __enter__(self) -> _RecordingCursor:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute(self, sql: str, params: tuple | list = ()) -> None:
        self.executions.append((sql, params))
        self.rowcount = 0

    def fetchall(self) -> list[Any]:
        if self._rows:
            return self._rows.pop(0)
        return []


class _RecordingClient:
    def __init__(self, rows_per_execute: list[list[Any]] | None = None) -> None:
        self.cursor_instance = _RecordingCursor(rows_per_execute)

    def cursor(self) -> _RecordingCursor:
        return self.cursor_instance


def test_sql_list_jobs_for_targets_sql_has_no_top_or_row_number() -> None:
    client = _RecordingClient()
    repo = SqlJobRepository(client)  # type: ignore[arg-type]
    repo.list_jobs_for_targets("aisle", ["a1", "a2"], job_type="process_aisle")
    assert len(client.cursor_instance.executions) == 1
    sql, params = client.cursor_instance.executions[0]
    assert "ROW_NUMBER" not in sql.upper()
    assert "TOP (" not in sql.upper()
    assert "SELECT *" not in sql.upper()
    assert "target_id IN" in sql
    assert "job_type = ?" in sql
    assert params[0] == "aisle"
    assert list(params[1:3]) == ["a1", "a2"]
    assert params[-1] == "process_aisle"


def test_sql_list_jobs_for_targets_batches_and_dedupes_input_ids() -> None:
    client = _RecordingClient()
    repo = SqlJobRepository(client)  # type: ignore[arg-type]
    ids = [f"aisle-{i}" for i in range(TARGET_ID_BATCH_SIZE + 3)]
    # Duplicate first id at end — must not increase batch load.
    ids_with_dup = [*ids, "aisle-0"]
    repo.list_jobs_for_targets("aisle", ids_with_dup, job_type="process_aisle")
    executions = client.cursor_instance.executions
    assert len(executions) == 2
    first_params = list(executions[0][1])
    second_params = list(executions[1][1])
    # target_type + batch ids + job_type
    assert len(first_params) == 1 + TARGET_ID_BATCH_SIZE + 1
    assert len(second_params) == 1 + 3 + 1
    assert first_params[1] == "aisle-0"
    assert second_params.count("aisle-0") == 0  # already in first batch after dedupe


def test_memory_case_a_multiple_runs_per_aisle() -> None:
    repo = MemoryJobRepository()
    for j in (
        _job("a1-1", "a1", offset_sec=1),
        _job("a1-2", "a1", offset_sec=2),
        _job("a1-3", "a1", offset_sec=3),
        _job("a2-1", "a2", offset_sec=1),
        _job("a2-2", "a2", offset_sec=2),
    ):
        repo.save(j)
    rows = repo.list_jobs_for_targets("aisle", ["a1", "a2"], job_type="process_aisle")
    assert len(rows) == 5


def test_memory_case_b_more_than_500_runs() -> None:
    repo = MemoryJobRepository()
    for i in range(501):
        repo.save(_job(f"j-{i}", "a1", cost="1", offset_sec=i))
    rows = repo.list_jobs_for_targets("aisle", ["a1"], job_type="process_aisle")
    assert len(rows) == 501
    assert sum_billable_costs_by_aisle_id(rows)["a1"] == Decimal("501")


def test_memory_case_c_duplicate_target_ids_no_duplicate_jobs() -> None:
    repo = MemoryJobRepository()
    repo.save(_job("j1", "a1"))
    repo.save(_job("j2", "a2"))
    rows = repo.list_jobs_for_targets("aisle", ["a1", "a1", "a2"], job_type="process_aisle")
    assert len(rows) == 2
    assert {j.id for j in rows} == {"j1", "j2"}


def test_memory_case_e_f_job_type_and_target_type_filters() -> None:
    repo = MemoryJobRepository()
    repo.save(_job("ok", "a1", job_type="process_aisle"))
    repo.save(_job("other-type", "a1", job_type="other"))
    repo.save(_job("other-target", "a1", target_type="inventory"))
    rows = repo.list_jobs_for_targets("aisle", ["a1"], job_type="process_aisle")
    assert [j.id for j in rows] == ["ok"]


def test_cases_g_h_i_billable_status_and_equal_costs() -> None:
    jobs = [
        _job("eq1", "a1", cost="10", offset_sec=1),
        _job("eq2", "a1", cost="10", offset_sec=2),
        _job("queued", "a1", cost="99", status=JobStatus.QUEUED, offset_sec=3),
        _job("running", "a1", cost="88", status=JobStatus.RUNNING, offset_sec=4),
        _job("failed", "a1", cost="3", status=JobStatus.FAILED, offset_sec=5),
        _job("canceled", "a1", cost="4", status=JobStatus.CANCELED, offset_sec=6),
        _job("timed", "a1", cost="5", status=JobStatus.TIMED_OUT, offset_sec=7),
    ]
    assert sum_billable_costs_by_aisle_id(jobs)["a1"] == 10 + 10 + 3 + 4 + 5
    assert billable_cost_for_job(jobs[2]) is None
    assert billable_cost_for_job(jobs[6]) is not None


def test_sql_optional_job_type_omits_filter() -> None:
    client = _RecordingClient()
    repo = SqlJobRepository(client)  # type: ignore[arg-type]
    repo.list_jobs_for_targets("aisle", ["a1"])
    sql, params = client.cursor_instance.executions[0]
    assert "job_type = ?" not in sql
    assert list(params) == ["aisle", "a1"]


def test_sql_uses_explicit_select_fields_compatible_with_row_mapper() -> None:
    """Empty fetch path still builds SQL with explicit columns (no SELECT *)."""
    client = _RecordingClient([[]])
    repo = SqlJobRepository(client)  # type: ignore[arg-type]
    assert repo.list_jobs_for_targets("aisle", ["a1"]) == []
    sql, _ = client.cursor_instance.executions[0]
    assert "FROM inventory_jobs" in sql
    assert "result_json" in sql
