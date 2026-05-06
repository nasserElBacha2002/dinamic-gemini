from __future__ import annotations

from datetime import datetime, timezone

from src.domain.jobs.entities import Job, JobStatus
from src.infrastructure.repositories.sql_job_repository import SqlJobRepository


class RecordingCursor:
    def __init__(self, rowcounts: list[int]) -> None:
        self._rowcounts = rowcounts
        self.executions: list[tuple[str, tuple]] = []
        self.rowcount = 0

    def __enter__(self) -> RecordingCursor:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def execute(self, sql: str, params: tuple = ()) -> None:
        self.executions.append((sql, params))
        if self._rowcounts:
            self.rowcount = self._rowcounts.pop(0)
        else:
            self.rowcount = 0


class RecordingClient:
    def __init__(self, rowcounts: list[int]) -> None:
        self.cursor_instance = RecordingCursor(rowcounts=rowcounts)

    def cursor(self) -> RecordingCursor:
        return self.cursor_instance


def _make_job() -> Job:
    now = datetime(2026, 3, 31, 12, 0, 0, tzinfo=timezone.utc)
    return Job(
        id="job-1",
        target_type="aisle",
        target_id="aisle-1",
        job_type="process_aisle",
        status=JobStatus.STARTING,
        payload_json={"aisle_id": "aisle-1"},
        created_at=now,
        updated_at=now,
        started_at=now,
        finished_at=None,
        last_heartbeat_at=now,
        cancel_requested_at=None,
        current_stage="worker_launch",
        current_substep="spawn_requested",
        current_step_started_at=now,
        attempt_count=1,
        retry_of_job_id="job-0",
        failure_code=None,
        failure_message=None,
        execution_id="exec-1",
    )


def test_save_insert_placeholder_count_matches_parameters_for_starting_job() -> None:
    client = RecordingClient(rowcounts=[0, 1])
    repo = SqlJobRepository(client)  # type: ignore[arg-type]

    repo.save(_make_job())

    assert len(client.cursor_instance.executions) == 2
    insert_sql, insert_params = client.cursor_instance.executions[1]
    assert "INSERT INTO inventory_jobs" in insert_sql
    assert insert_sql.count("?") == len(insert_params) == 27


def test_save_update_placeholder_count_matches_parameters() -> None:
    client = RecordingClient(rowcounts=[1])
    repo = SqlJobRepository(client)  # type: ignore[arg-type]

    repo.save(_make_job())

    assert len(client.cursor_instance.executions) == 1
    update_sql, update_params = client.cursor_instance.executions[0]
    assert "UPDATE inventory_jobs" in update_sql
    assert update_sql.count("?") == len(update_params) == 26
