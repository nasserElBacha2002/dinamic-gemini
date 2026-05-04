from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from src.domain.jobs.entities import Job, JobStatus
from src.jobs import worker_bootstrap


class StubJobRepo:
    def __init__(self, job: Job) -> None:
        self.job = job

    def get_by_id(self, job_id: str) -> Job | None:
        return self.job if self.job.id == job_id else None

    def save(self, job: Job) -> None:
        self.job = job


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
        execution_id="exec-1",
    )


def test_checkpoint_v3_job_bootstrap_updates_stage_and_heartbeat(
    monkeypatch, tmp_path: Path
) -> None:
    repo = StubJobRepo(_make_job())
    monkeypatch.setattr(
        worker_bootstrap, "load_settings", lambda: type("S", (), {"output_dir": str(tmp_path)})()
    )
    monkeypatch.setattr("src.runtime.v3_deps.get_job_repo", lambda: repo)

    worker_bootstrap.checkpoint_v3_job_bootstrap(
        job_id="job-1",
        execution_id="exec-1",
        substep="job_load_completed",
    )

    updated = repo.job
    assert updated.current_stage == "worker_bootstrap"
    assert updated.current_substep == "job_load_completed"
    assert updated.last_heartbeat_at is not None
    assert updated.execution_id == "exec-1"


def test_fail_v3_job_bootstrap_marks_job_failed(monkeypatch, tmp_path: Path) -> None:
    repo = StubJobRepo(_make_job())
    monkeypatch.setattr(
        worker_bootstrap, "load_settings", lambda: type("S", (), {"output_dir": str(tmp_path)})()
    )
    monkeypatch.setattr("src.runtime.v3_deps.get_job_repo", lambda: repo)

    worker_bootstrap.fail_v3_job_bootstrap(
        job_id="job-1",
        execution_id="exec-1",
        error_message="bootstrap exploded",
        substep="executor_bootstrap_failed",
    )

    updated = repo.job
    assert updated.status == JobStatus.FAILED
    assert updated.current_stage == "worker_bootstrap"
    assert updated.current_substep == "executor_bootstrap_failed"
    assert updated.failure_code == worker_bootstrap.BOOTSTRAP_FAILURE_CODE
    assert updated.failure_message == "bootstrap exploded"
    assert updated.finished_at is not None
