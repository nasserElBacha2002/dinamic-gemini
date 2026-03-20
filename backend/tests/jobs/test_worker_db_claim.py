from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Optional

from src.jobs import job_store
from src.jobs.models import JobInput, JobRecord, JobStatus
from src.jobs.worker import worker_loop
from src.domain.jobs.entities import Job as V3Job
from src.domain.jobs.entities import JobStatus as V3JobStatus


def _make_job(job_id: str, status: JobStatus = JobStatus.QUEUED) -> JobRecord:
    return JobRecord(
        job_id=job_id,
        input=JobInput(video_path="/tmp/video.mp4", mode="hybrid", confidence_threshold=0.7),
        status=status,
        progress={"stage": "", "percent": 0},
        output=None,
        error=None,
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
    )


def test_claim_next_job_prefers_db_claim(monkeypatch) -> None:
    class FakeJobsRepo:
        def claim_next_queued_job(self):
            return {
                "job_id": "job-db-1",
                "input": {
                    "video_path": "/tmp/video.mp4",
                    "mode": "hybrid",
                    "confidence_threshold": 0.7,
                },
                "status": "running",
                "progress": {"stage": "claimed", "percent": 1},
                "output": None,
                "error": None,
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:01Z",
            }

    monkeypatch.setattr(job_store, "_db_repos", lambda: (FakeJobsRepo(), None, None))

    claimed = job_store.claim_next_job(Path("output"))
    assert claimed is not None
    assert claimed.job_id == "job-db-1"
    assert claimed.status == JobStatus.RUNNING
    assert claimed.progress.percent == 1


def test_claim_next_job_prefers_v3_inventory_jobs_claim(monkeypatch) -> None:
    v3_claimed = V3Job(
        id="v3-job-1",
        target_type="aisle",
        target_id="a-1",
        job_type="process_aisle",
        status=V3JobStatus.RUNNING,
        payload_json={"aisle_id": "a-1"},
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 1, 0, 0, 1, tzinfo=timezone.utc),
    )

    class FakeV3Repo:
        def claim_next_queued_job(self):
            return v3_claimed

    monkeypatch.setattr("src.runtime.v3_deps.get_job_repo", lambda: FakeV3Repo())
    monkeypatch.setattr(job_store, "_db_repos", lambda: None)
    monkeypatch.setattr(
        job_store,
        "load_settings",
        lambda: SimpleNamespace(sqlserver_enabled=True, sqlserver_connection_string="Driver=ok"),
    )

    claimed = job_store.claim_next_job(Path("output"))
    assert claimed is not None
    assert claimed.job_id == "v3-job-1"
    assert claimed.status == JobStatus.RUNNING
    assert claimed.progress.percent == 1


def test_claim_next_job_reclaims_stale_running_before_claim(monkeypatch, caplog) -> None:
    class FakeV3Repo:
        def __init__(self) -> None:
            self.reclaimed = 0

        def reclaim_stale_running_jobs(self, stale_after_seconds: int):
            assert stale_after_seconds == 900
            self.reclaimed += 1
            return 2

        def claim_next_queued_job(self):
            return None

    repo = FakeV3Repo()
    monkeypatch.setattr("src.runtime.v3_deps.get_job_repo", lambda: repo)
    monkeypatch.setattr(job_store, "_db_repos", lambda: None)
    monkeypatch.setattr(
        job_store,
        "load_settings",
        lambda: SimpleNamespace(
            sqlserver_enabled=True,
            sqlserver_connection_string="Driver=ok",
            worker_stale_running_timeout_sec=900,
        ),
    )
    with caplog.at_level(logging.WARNING):
        claimed = job_store.claim_next_job(Path("output"))

    assert claimed is None
    assert repo.reclaimed == 1
    assert "Reclaimed stale RUNNING v3 jobs before claim" in caplog.text


def test_claim_next_job_legacy_fallback_when_db_disabled(monkeypatch) -> None:
    monkeypatch.setattr(job_store, "_db_repos", lambda: None)
    monkeypatch.setattr(
        job_store,
        "load_settings",
        lambda: SimpleNamespace(sqlserver_enabled=False, sqlserver_connection_string=""),
    )
    monkeypatch.setattr("src.jobs.queue.dequeue", lambda timeout=0.1: "job-local-1")
    monkeypatch.setattr(job_store, "get_job", lambda base, job_id: _make_job(job_id))

    claimed = job_store.claim_next_job(Path("output"))
    assert claimed is not None
    assert claimed.job_id == "job-local-1"
    assert claimed.status == JobStatus.QUEUED


def test_worker_loop_uses_claim_next_job(monkeypatch) -> None:
    claimed: list[Optional[JobRecord]] = [_make_job("job-a"), None]
    processed: list[str] = []
    stop_state = {"calls": 0}

    def fake_claim_next_job(_base: Path) -> Optional[JobRecord]:
        if claimed:
            return claimed.pop(0)
        return None

    def fake_run_job(_base: Path, job_id: str) -> None:
        processed.append(job_id)

    def fake_stop() -> bool:
        stop_state["calls"] += 1
        return stop_state["calls"] > 3

    monkeypatch.setattr("src.jobs.worker.claim_next_job", fake_claim_next_job)
    monkeypatch.setattr("src.jobs.worker.run_job", fake_run_job)
    monkeypatch.setattr("src.jobs.worker.time.sleep", lambda _s: None)

    worker_loop(Path("output"), stop=fake_stop)
    assert processed == ["job-a"]


def test_claim_next_job_logs_exception_when_db_claim_fails(monkeypatch, caplog) -> None:
    class FailingJobsRepo:
        def claim_next_queued_job(self):
            raise RuntimeError("db claim boom")

    monkeypatch.setattr(job_store, "_db_repos", lambda: (FailingJobsRepo(), None, None))
    monkeypatch.setattr(
        job_store,
        "load_settings",
        lambda: SimpleNamespace(sqlserver_enabled=True, sqlserver_connection_string="Driver=ok"),
    )
    with caplog.at_level(logging.ERROR):
        claimed = job_store.claim_next_job(Path("output"))

    assert claimed is None
    assert "DB claim_next_queued_job failed while SQL worker mode is enabled" in caplog.text


def test_claim_next_job_logs_error_when_sql_mode_configured_but_repos_unavailable(
    monkeypatch, caplog
) -> None:
    monkeypatch.setattr(job_store, "_db_repos", lambda: None)
    monkeypatch.setattr(
        job_store,
        "load_settings",
        lambda: SimpleNamespace(sqlserver_enabled=True, sqlserver_connection_string="Driver=ok"),
    )
    with caplog.at_level(logging.ERROR):
        claimed = job_store.claim_next_job(Path("output"))

    assert claimed is None
    assert "SQL worker mode configured but DB repositories are unavailable" in caplog.text

