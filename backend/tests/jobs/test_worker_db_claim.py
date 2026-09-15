from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.domain.jobs.entities import Job as V3Job
from src.domain.jobs.entities import JobStatus as V3JobStatus
from src.jobs import job_store
from src.jobs.claim_cycle import (
    WorkerClaimCycleResult,
    WorkerClaimCycleStatus,
)
from src.jobs.models import JobInput, JobRecord, JobStatus
from src.jobs.worker import worker_loop
from src.jobs.worker_runtime import (
    REASON_LEGACY_CLAIM_FAILED,
    REASON_V3_JOB_REPOSITORY_UNAVAILABLE,
    REASON_WORKER_STARTING,
    get_embedded_worker_runtime,
    reset_embedded_worker_runtime_for_tests,
)


@pytest.fixture(autouse=True)
def _reset_worker_runtime() -> None:
    reset_embedded_worker_runtime_for_tests()
    job_store.reset_claim_throttle_for_tests()


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


def _sql_settings(**extra: object) -> SimpleNamespace:
    base = dict(
        sqlserver_enabled=True,
        sqlserver_connection_string="Driver=ok",
        legacy_stage8_sql_bridge_disabled=True,
        worker_stale_running_timeout_sec=0,
        worker_stale_reclaim_interval_sec=0,
    )
    base.update(extra)
    return SimpleNamespace(**base)


def test_claim_cycle_result_invariants_reject_invalid_shapes() -> None:
    with pytest.raises(ValueError, match="JOB_CLAIMED"):
        WorkerClaimCycleResult(status=WorkerClaimCycleStatus.JOB_CLAIMED, job=None)
    with pytest.raises(ValueError, match="IDLE_HEALTHY"):
        WorkerClaimCycleResult(
            status=WorkerClaimCycleStatus.IDLE_HEALTHY, job=_make_job("x")
        )
    with pytest.raises(ValueError, match="CLAIM_UNAVAILABLE"):
        WorkerClaimCycleResult(
            status=WorkerClaimCycleStatus.CLAIM_UNAVAILABLE, job=_make_job("x")
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

    class NoV3Claim:
        pass

    monkeypatch.setattr("src.runtime.v3_deps.get_job_repo", lambda: NoV3Claim())
    monkeypatch.setattr(job_store, "_db_repos", lambda: (FakeJobsRepo(), None, None))
    monkeypatch.setattr(
        job_store,
        "load_settings",
        lambda: _sql_settings(legacy_stage8_sql_bridge_disabled=False),
    )

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
    monkeypatch.setattr(job_store, "load_settings", lambda: _sql_settings())

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
        lambda: _sql_settings(
            worker_stale_running_timeout_sec=900,
            worker_stale_reclaim_interval_sec=0,
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


def test_worker_loop_job_claimed_runs_once(monkeypatch) -> None:
    from src.jobs.claim_cycle import WorkerClaimCycleResult

    cycles = [
        WorkerClaimCycleResult(
            status=WorkerClaimCycleStatus.JOB_CLAIMED, job=_make_job("job-a")
        ),
        WorkerClaimCycleResult(status=WorkerClaimCycleStatus.IDLE_HEALTHY, detail="done"),
    ]
    processed: list[str] = []
    stop_state = {"calls": 0}

    def fake_cycle(_base: Path) -> WorkerClaimCycleResult:
        if cycles:
            return cycles.pop(0)
        return WorkerClaimCycleResult(status=WorkerClaimCycleStatus.IDLE_HEALTHY)

    def fake_run_job(_base: Path, job_id: str) -> None:
        processed.append(job_id)

    def fake_stop() -> bool:
        stop_state["calls"] += 1
        return stop_state["calls"] > 3

    monkeypatch.setattr("src.jobs.worker.claim_next_job_cycle", fake_cycle)
    monkeypatch.setattr("src.jobs.worker.run_job", fake_run_job)
    monkeypatch.setattr("src.jobs.worker.time.sleep", lambda _s: None)

    worker_loop(Path("output"), stop=fake_stop)
    assert processed == ["job-a"]
    assert get_embedded_worker_runtime().snapshot().unavailable_reason is None


def test_worker_loop_idle_healthy_does_not_process(monkeypatch) -> None:
    processed: list[str] = []
    stop_state = {"n": 0}

    def idle(_base: Path) -> WorkerClaimCycleResult:
        return WorkerClaimCycleResult(
            status=WorkerClaimCycleStatus.IDLE_HEALTHY, detail="idle"
        )

    def fake_stop() -> bool:
        stop_state["n"] += 1
        return stop_state["n"] > 2

    monkeypatch.setattr("src.jobs.worker.claim_next_job_cycle", idle)
    monkeypatch.setattr(
        "src.jobs.worker.run_job", lambda *_a, **_k: processed.append("x")
    )
    monkeypatch.setattr("src.jobs.worker.time.sleep", lambda _s: None)

    worker_loop(Path("output"), stop=fake_stop)
    assert processed == []
    snap = get_embedded_worker_runtime().snapshot()
    assert snap.last_success_monotonic is not None
    assert snap.unavailable_reason is None


def test_worker_loop_claim_unavailable_marks_runtime(monkeypatch) -> None:
    stop_state = {"n": 0}

    def unavailable(_base: Path) -> WorkerClaimCycleResult:
        return WorkerClaimCycleResult(
            status=WorkerClaimCycleStatus.CLAIM_UNAVAILABLE,
            detail=REASON_V3_JOB_REPOSITORY_UNAVAILABLE,
            error_type="RuntimeError",
        )

    def fake_stop() -> bool:
        stop_state["n"] += 1
        return stop_state["n"] > 1

    monkeypatch.setattr("src.jobs.worker.claim_next_job_cycle", unavailable)
    monkeypatch.setattr("src.jobs.worker.time.sleep", lambda _s: None)

    worker_loop(Path("output"), stop=fake_stop)
    snap = get_embedded_worker_runtime().snapshot()
    assert snap.unavailable_reason == REASON_V3_JOB_REPOSITORY_UNAVAILABLE
    assert snap.failure_count >= 1


def test_memory_dequeue_exception_is_not_idle(monkeypatch) -> None:
    monkeypatch.setattr(
        job_store,
        "load_settings",
        lambda: SimpleNamespace(sqlserver_enabled=False, sqlserver_connection_string=""),
    )

    def boom_dequeue(**_kwargs):
        raise RuntimeError("queue boom")

    monkeypatch.setattr("src.jobs.queue.dequeue", boom_dequeue)
    result = job_store.claim_next_job_cycle(Path("output"))
    assert result.status == WorkerClaimCycleStatus.CLAIM_UNAVAILABLE
    assert result.detail == "memory_queue_failed"


def test_v3_without_claim_method_and_legacy_failing_is_unavailable(monkeypatch) -> None:
    class NoClaimV3:
        pass

    class BoomLegacy:
        def claim_next_queued_job(self):
            raise RuntimeError("legacy down")

    monkeypatch.setattr("src.runtime.v3_deps.get_job_repo", lambda: NoClaimV3())
    monkeypatch.setattr(job_store, "_db_repos", lambda: (BoomLegacy(), None, None))
    monkeypatch.setattr(
        job_store,
        "load_settings",
        lambda: _sql_settings(legacy_stage8_sql_bridge_disabled=False),
    )
    result = job_store.claim_next_job_cycle(Path("output"))
    assert result.status == WorkerClaimCycleStatus.CLAIM_UNAVAILABLE
    assert result.detail == REASON_LEGACY_CLAIM_FAILED


def test_claim_cycle_v3_idle_does_not_invoke_db_repos_when_legacy_disabled(monkeypatch) -> None:
    class IdleV3Repo:
        def claim_next_queued_job(self):
            return None

    calls = {"n": 0}

    def _db_repos_should_not_run() -> None:
        calls["n"] += 1
        raise AssertionError("_db_repos must not be called when legacy bridge is disabled")

    monkeypatch.setattr("src.runtime.v3_deps.get_job_repo", lambda: IdleV3Repo())
    monkeypatch.setattr(job_store, "_db_repos", _db_repos_should_not_run)
    monkeypatch.setattr(job_store, "load_settings", lambda: _sql_settings())
    result = job_store.claim_next_job_cycle(Path("output"))
    assert result.status == WorkerClaimCycleStatus.IDLE_HEALTHY
    assert result.job is None
    assert calls["n"] == 0


def test_legacy_drain_required_broken_is_unavailable(monkeypatch, caplog) -> None:
    class IdleV3Repo:
        def claim_next_queued_job(self):
            return None

    class BoomLegacy:
        def claim_next_queued_job(self):
            raise RuntimeError("Invalid object name 'jobs'")

    monkeypatch.setattr("src.runtime.v3_deps.get_job_repo", lambda: IdleV3Repo())
    monkeypatch.setattr(job_store, "_db_repos", lambda: (BoomLegacy(), None, None))
    monkeypatch.setattr(
        job_store,
        "load_settings",
        lambda: _sql_settings(legacy_stage8_sql_bridge_disabled=False),
    )
    with caplog.at_level(logging.ERROR):
        result = job_store.claim_next_job_cycle(Path("output"))

    assert result.status == WorkerClaimCycleStatus.CLAIM_UNAVAILABLE
    assert result.detail == REASON_LEGACY_CLAIM_FAILED
    assert "Invalid object name" in caplog.text or "DB claim_next_queued_job failed" in caplog.text


def test_legacy_drain_required_empty_is_idle(monkeypatch) -> None:
    class IdleV3Repo:
        def claim_next_queued_job(self):
            return None

    class EmptyLegacy:
        def claim_next_queued_job(self):
            return None

    monkeypatch.setattr("src.runtime.v3_deps.get_job_repo", lambda: IdleV3Repo())
    monkeypatch.setattr(job_store, "_db_repos", lambda: (EmptyLegacy(), None, None))
    monkeypatch.setattr(
        job_store,
        "load_settings",
        lambda: _sql_settings(legacy_stage8_sql_bridge_disabled=False),
    )
    result = job_store.claim_next_job_cycle(Path("output"))
    assert result.status == WorkerClaimCycleStatus.IDLE_HEALTHY
    assert result.job is None


def test_legacy_drain_required_with_job_is_claimed(monkeypatch) -> None:
    class IdleV3Repo:
        def claim_next_queued_job(self):
            return None

    class LegacyWithJob:
        def claim_next_queued_job(self):
            return {
                "job_id": "legacy-1",
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

    monkeypatch.setattr("src.runtime.v3_deps.get_job_repo", lambda: IdleV3Repo())
    monkeypatch.setattr(job_store, "_db_repos", lambda: (LegacyWithJob(), None, None))
    monkeypatch.setattr(
        job_store,
        "load_settings",
        lambda: _sql_settings(legacy_stage8_sql_bridge_disabled=False),
    )
    result = job_store.claim_next_job_cycle(Path("output"))
    assert result.status == WorkerClaimCycleStatus.JOB_CLAIMED
    assert result.job is not None
    assert result.job.job_id == "legacy-1"


def test_legacy_failure_log_is_rate_limited(monkeypatch, caplog) -> None:
    class IdleV3Repo:
        def claim_next_queued_job(self):
            return None

    class BoomLegacy:
        def claim_next_queued_job(self):
            raise RuntimeError("legacy down")

    monkeypatch.setattr("src.runtime.v3_deps.get_job_repo", lambda: IdleV3Repo())
    monkeypatch.setattr(job_store, "_db_repos", lambda: (BoomLegacy(), None, None))
    monkeypatch.setattr(
        job_store,
        "load_settings",
        lambda: _sql_settings(legacy_stage8_sql_bridge_disabled=False),
    )
    with caplog.at_level(logging.ERROR):
        for _ in range(3):
            assert (
                job_store.claim_next_job_cycle(Path("output")).status
                == WorkerClaimCycleStatus.CLAIM_UNAVAILABLE
            )
    # First failure: exception + traceback; repeats within interval: error_type only.
    assert caplog.text.count("Traceback") == 1
    assert caplog.text.count("error_type=RuntimeError") == 2


def test_worker_loop_recovers_after_unavailable(monkeypatch, caplog) -> None:
    state = {"fail": True}
    stop_state = {"n": 0}

    def flip(_base: Path) -> WorkerClaimCycleResult:
        if state["fail"]:
            return WorkerClaimCycleResult(
                status=WorkerClaimCycleStatus.CLAIM_UNAVAILABLE,
                detail=REASON_V3_JOB_REPOSITORY_UNAVAILABLE,
            )
        return WorkerClaimCycleResult(
            status=WorkerClaimCycleStatus.IDLE_HEALTHY, detail="recovered"
        )

    def fake_stop() -> bool:
        stop_state["n"] += 1
        if stop_state["n"] == 2:
            state["fail"] = False
        return stop_state["n"] > 3

    monkeypatch.setattr("src.jobs.worker.claim_next_job_cycle", flip)
    monkeypatch.setattr("src.jobs.worker.time.sleep", lambda _s: None)

    with caplog.at_level(logging.INFO):
        worker_loop(Path("output"), stop=fake_stop)

    assert "job_worker_recovered" in caplog.text
    assert get_embedded_worker_runtime().snapshot().unavailable_reason is None
    assert get_embedded_worker_runtime().snapshot().recovery_count == 1


def test_v3_exception_does_not_silently_fall_through_to_legacy(monkeypatch) -> None:
    class LegacyWouldWin:
        def claim_next_queued_job(self):
            return {
                "job_id": "should-not-claim",
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

    def _boom_v3() -> None:
        raise RuntimeError("v3 down")

    monkeypatch.setattr("src.runtime.v3_deps.get_job_repo", _boom_v3)
    monkeypatch.setattr(job_store, "_db_repos", lambda: (LegacyWouldWin(), None, None))
    monkeypatch.setattr(
        job_store,
        "load_settings",
        lambda: _sql_settings(legacy_stage8_sql_bridge_disabled=False),
    )
    result = job_store.claim_next_job_cycle(Path("output"))
    assert result.status == WorkerClaimCycleStatus.CLAIM_UNAVAILABLE
    assert result.detail == REASON_V3_JOB_REPOSITORY_UNAVAILABLE
    assert result.job is None


def test_claim_cycle_sql_mode_without_claimable_repo_returns_unavailable(monkeypatch) -> None:
    monkeypatch.setattr("src.runtime.v3_deps.get_job_repo", lambda: object())
    monkeypatch.setattr(job_store, "_db_repos", lambda: None)
    monkeypatch.setattr(job_store, "load_settings", lambda: _sql_settings())
    result = job_store.claim_next_job_cycle(Path("output"))
    assert result.status == WorkerClaimCycleStatus.CLAIM_UNAVAILABLE
    assert result.detail == REASON_V3_JOB_REPOSITORY_UNAVAILABLE


def test_claim_cycle_v3_failure_returns_unavailable_without_marking_runtime(
    monkeypatch, caplog
) -> None:
    def _boom_v3_repo() -> None:
        raise RuntimeError("v3 repo missing")

    monkeypatch.setattr("src.runtime.v3_deps.get_job_repo", _boom_v3_repo)
    monkeypatch.setattr(job_store, "_db_repos", lambda: None)
    monkeypatch.setattr(job_store, "load_settings", lambda: _sql_settings())
    with caplog.at_level(logging.ERROR):
        result = job_store.claim_next_job_cycle(Path("output"))
    assert result.status == WorkerClaimCycleStatus.CLAIM_UNAVAILABLE
    assert result.detail == REASON_V3_JOB_REPOSITORY_UNAVAILABLE
    # Side effects live in worker_loop, not job_store.
    assert get_embedded_worker_runtime().snapshot().unavailable_reason is None


def test_claim_cycle_v3_job_skips_legacy(monkeypatch) -> None:
    v3_claimed = V3Job(
        id="v3-only",
        target_type="aisle",
        target_id="a-1",
        job_type="process_aisle",
        status=V3JobStatus.RUNNING,
        payload_json={},
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    class FakeV3Repo:
        def claim_next_queued_job(self):
            return v3_claimed

    calls = {"n": 0}

    def _count_db_repos():
        calls["n"] += 1
        return None

    monkeypatch.setattr("src.runtime.v3_deps.get_job_repo", lambda: FakeV3Repo())
    monkeypatch.setattr(job_store, "_db_repos", _count_db_repos)
    monkeypatch.setattr(
        job_store,
        "load_settings",
        lambda: _sql_settings(legacy_stage8_sql_bridge_disabled=False),
    )
    result = job_store.claim_next_job_cycle(Path("output"))
    assert result.status == WorkerClaimCycleStatus.JOB_CLAIMED
    assert result.job is not None and result.job.job_id == "v3-only"
    assert calls["n"] == 0


def test_thread_alive_without_first_cycle_is_starting() -> None:
    import threading

    runtime = get_embedded_worker_runtime()
    runtime.configure(required=True, sql_mode=True)

    def _block() -> None:
        while not runtime.should_stop():
            import time

            time.sleep(0.01)

    thread = threading.Thread(target=_block, daemon=True)
    runtime.mark_started(thread)
    thread.start()
    problem = runtime.readiness_problem()
    assert problem is not None
    assert problem[1] == REASON_WORKER_STARTING
    runtime.request_stop()
    runtime.join(timeout_sec=2.0)
