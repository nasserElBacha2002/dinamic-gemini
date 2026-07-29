"""Phase 5 corrections — RecoverStaleJobUseCase (memory + concurrent)."""

from __future__ import annotations

import threading
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from src.application.services.aisle_job_launch_service import AisleJobLaunchService
from src.application.services.inventory_status_reconciler import InventoryStatusReconciler
from src.application.use_cases.recovery.recover_stale_job import (
    RecoverStaleJobCommand,
    RecoverStaleJobOutcome,
    RecoverStaleJobUseCase,
)
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.aisle_identification.modes import (
    AisleIdentificationExecutionStrategy,
    AisleIdentificationMode,
    AisleIdentificationModeSource,
)
from src.domain.inventory.entities import Inventory, InventoryProcessingMode, InventoryStatus
from src.domain.jobs.entities import Job, JobStatus
from src.infrastructure.repositories.memory_aisle_repository import MemoryAisleRepository
from src.infrastructure.repositories.memory_inventory_repository import MemoryInventoryRepository
from src.infrastructure.repositories.memory_job_repository import MemoryJobRepository
from src.observability.metrics.registry import get_metrics_registry


class _FixedClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


class _FakeWorkerLaunch:
    def __init__(self) -> None:
        self.launches: list[str] = []
        self.idempotent_launches: list[tuple[str, str]] = []
        self.fail = False
        self.relaunch_fail = False
        self._idempotency_keys: set[str] = set()
        self._lock = threading.Lock()

    def launch(self, job_id: str) -> str:
        if self.fail:
            from src.application.errors import WorkerLaunchFailedError

            raise WorkerLaunchFailedError("spawn refused", job_id=job_id)
        self.launches.append(job_id)
        return f"exec-{job_id}"

    def launch_job_if_not_launched(self, job_id: str, *, idempotency_key: str) -> str:
        with self._lock:
            if idempotency_key in self._idempotency_keys:
                return f"exec-relaunch-{job_id}"
            if self.relaunch_fail:
                from src.application.errors import WorkerLaunchFailedError

                raise WorkerLaunchFailedError("relaunch refused", job_id=job_id)
            self._idempotency_keys.add(idempotency_key)
        self.idempotent_launches.append((job_id, idempotency_key))
        return f"exec-relaunch-{job_id}"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _build_uc(*, worker: _FakeWorkerLaunch | None = None, now: datetime | None = None):
    now = now or _now()
    clock = _FixedClock(now)
    aisle_repo = MemoryAisleRepository()
    job_repo = MemoryJobRepository(aisle_repo=aisle_repo)
    inv_repo = MemoryInventoryRepository()
    worker = worker or _FakeWorkerLaunch()
    launch = AisleJobLaunchService(
        aisle_repo=aisle_repo,
        job_repo=job_repo,
        worker_launch_service=worker,
        clock=clock,
        status_reconciler=InventoryStatusReconciler(
            inventory_repo=inv_repo, aisle_repo=aisle_repo, clock=clock
        ),
    )
    uc = RecoverStaleJobUseCase(
        job_repo=job_repo,
        aisle_repo=aisle_repo,
        launch_service=launch,
        clock=clock,
    )
    return uc, job_repo, aisle_repo, inv_repo, worker, clock, now


def _seed_stale(*, job_repo, aisle_repo, inv_repo, now: datetime, attempt_count: int = 1, correlation: str = "corr-root-1"):
    suffix = uuid.uuid4().hex[:8]
    inv_id = f"inv-{suffix}"
    aisle_id = f"aisle-{suffix}"
    job_id = f"job-{suffix}"
    old = now - timedelta(hours=2)
    inv_repo.save(
        Inventory(
            id=inv_id,
            name="R",
            status=InventoryStatus.PROCESSING,
            created_at=old,
            updated_at=old,
            processing_mode=InventoryProcessingMode.TEST,
        )
    )
    aisle = Aisle(
        id=aisle_id,
        inventory_id=inv_id,
        code=f"A{suffix[:4]}",
        status=AisleStatus.PROCESSING,
        created_at=old,
        updated_at=old,
    )
    aisle_repo.save(aisle)
    job = Job(
        id=job_id,
        target_type="aisle",
        target_id=aisle_id,
        job_type="process_aisle",
        status=JobStatus.RUNNING,
        payload_json={"aisle_id": aisle_id, "correlation_id": correlation},
        created_at=old,
        updated_at=old,
        started_at=old,
        last_heartbeat_at=old,
        attempt_count=attempt_count,
        claim_owner_id="owner-dead",
        lease_expires_at=old,
        provider_name="gemini",
        identification_mode=AisleIdentificationMode.INTERNAL_OCR,
        identification_mode_source=AisleIdentificationModeSource.SYSTEM_DEFAULT,
        execution_strategy=AisleIdentificationExecutionStrategy.INTERNAL_OCR,
    )
    job_repo.save(job)
    return job, aisle


def _seed_stale_parent_with_child(
    *,
    job_repo,
    aisle_repo,
    inv_repo,
    now: datetime,
    child_status: JobStatus,
    child_failure_code: str | None = None,
    parent_stale_failed: bool = False,
) -> tuple[Job, Job, Aisle]:
    parent, aisle = _seed_stale(
        job_repo=job_repo, aisle_repo=aisle_repo, inv_repo=inv_repo, now=now
    )
    if parent_stale_failed:
        parent.status = JobStatus.FAILED
        parent.failure_code = "STALE_JOB"
        parent.finished_at = now
        parent.updated_at = now
        job_repo.save(parent)

    child = Job(
        id=f"child-{uuid.uuid4().hex[:8]}",
        target_type="aisle",
        target_id=aisle.id,
        job_type="process_aisle",
        status=child_status,
        payload_json=dict(parent.payload_json or {}),
        created_at=now,
        updated_at=now,
        started_at=now,
        attempt_count=2,
        retry_of_job_id=parent.id,
        failure_code=child_failure_code,
        failure_message=child_failure_code,
        execution_id="exec-child-live" if child_status == JobStatus.RUNNING else None,
        provider_name="gemini",
        identification_mode=AisleIdentificationMode.INTERNAL_OCR,
        identification_mode_source=AisleIdentificationModeSource.SYSTEM_DEFAULT,
        execution_strategy=AisleIdentificationExecutionStrategy.INTERNAL_OCR,
    )
    job_repo.save(child)
    return parent, child, aisle


def test_recover_creates_new_attempt_and_launches_worker() -> None:
    get_metrics_registry().reset_for_tests()
    uc, job_repo, aisle_repo, inv_repo, worker, _clock, now = _build_uc()
    job, _aisle = _seed_stale(job_repo=job_repo, aisle_repo=aisle_repo, inv_repo=inv_repo, now=now)
    result = uc.execute(
        RecoverStaleJobCommand(
            job_id=job.id,
            actor="test",
            reason="stale",
            dry_run=False,
            stale_after_seconds=60,
            max_attempts=3,
        )
    )
    assert result.outcome == RecoverStaleJobOutcome.RECOVERED
    assert result.new_job_id
    child = job_repo.get_by_id(result.new_job_id)
    assert child is not None
    assert child.retry_of_job_id == job.id
    assert child.payload_json.get("correlation_id") == "corr-root-1"
    assert worker.launches == [child.id]
    parent = job_repo.get_by_id(job.id)
    assert parent is not None
    assert parent.status == JobStatus.FAILED


def test_two_recoverers_one_child_one_launch() -> None:
    uc, job_repo, aisle_repo, inv_repo, worker, _clock, now = _build_uc()
    job, _aisle = _seed_stale(job_repo=job_repo, aisle_repo=aisle_repo, inv_repo=inv_repo, now=now)
    barrier = threading.Barrier(2)
    results: list[Any] = []
    lock = threading.Lock()

    def run() -> None:
        barrier.wait()
        r = uc.execute(
            RecoverStaleJobCommand(
                job_id=job.id,
                actor="t",
                reason="stale",
                dry_run=False,
                stale_after_seconds=60,
                max_attempts=3,
            )
        )
        with lock:
            results.append(r)

    threads = [threading.Thread(target=run) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    recovered = [r for r in results if r.outcome == RecoverStaleJobOutcome.RECOVERED]
    already = [r for r in results if r.outcome == RecoverStaleJobOutcome.ALREADY_RECOVERED]
    lost = [r for r in results if r.outcome == RecoverStaleJobOutcome.LOST_CAS]
    assert len(recovered) == 1
    assert len(already) + len(lost) == 1
    children = job_repo.list_jobs_by_retry_of(job.id)
    assert len(children) == 1
    assert len(worker.launches) == 1


def test_max_attempts_and_active_lease() -> None:
    uc, job_repo, aisle_repo, inv_repo, worker, clock, now = _build_uc()
    job, _aisle = _seed_stale(
        job_repo=job_repo, aisle_repo=aisle_repo, inv_repo=inv_repo, now=now, attempt_count=3
    )
    r = uc.execute(
        RecoverStaleJobCommand(
            job_id=job.id, actor="t", reason="stale", dry_run=False, stale_after_seconds=60, max_attempts=3
        )
    )
    assert r.outcome == RecoverStaleJobOutcome.MAX_ATTEMPTS

    job2, _ = _seed_stale(job_repo=job_repo, aisle_repo=aisle_repo, inv_repo=inv_repo, now=now)
    job2.lease_expires_at = now + timedelta(minutes=10)
    job2.last_heartbeat_at = now
    job2.updated_at = now
    job_repo.save(job2)
    r2 = uc.execute(
        RecoverStaleJobCommand(
            job_id=job2.id, actor="t", reason="stale", dry_run=False, stale_after_seconds=60, max_attempts=5
        )
    )
    assert r2.outcome == RecoverStaleJobOutcome.ACTIVE_LEASE
    assert worker.launches == []


def test_dry_run_and_launch_failure() -> None:
    uc, job_repo, aisle_repo, inv_repo, worker, _clock, now = _build_uc()
    job, _ = _seed_stale(job_repo=job_repo, aisle_repo=aisle_repo, inv_repo=inv_repo, now=now)
    dry = uc.execute(
        RecoverStaleJobCommand(
            job_id=job.id, actor="t", reason="stale", dry_run=True, stale_after_seconds=60, max_attempts=3
        )
    )
    assert dry.outcome == RecoverStaleJobOutcome.DRY_RUN
    assert not job_repo.list_jobs_by_retry_of(job.id)

    worker.fail = True
    failed = uc.execute(
        RecoverStaleJobCommand(
            job_id=job.id, actor="t", reason="stale", dry_run=False, stale_after_seconds=60, max_attempts=3
        )
    )
    assert failed.outcome == RecoverStaleJobOutcome.WORKER_LAUNCH_FAILED
    child = job_repo.list_jobs_by_retry_of(job.id)[0]
    assert child.status == JobStatus.FAILED
    assert child.failure_code == "WORKER_LAUNCH_FAILED"


def test_launch_failure_then_relaunch() -> None:
    uc, job_repo, aisle_repo, inv_repo, worker, _clock, now = _build_uc()
    job, _ = _seed_stale(job_repo=job_repo, aisle_repo=aisle_repo, inv_repo=inv_repo, now=now)
    worker.fail = True
    first = uc.execute(
        RecoverStaleJobCommand(
            job_id=job.id, actor="t", reason="stale", dry_run=False, stale_after_seconds=60, max_attempts=3
        )
    )
    assert first.outcome == RecoverStaleJobOutcome.WORKER_LAUNCH_FAILED
    child = job_repo.list_jobs_by_retry_of(job.id)[0]

    worker.fail = False
    second = uc.execute(
        RecoverStaleJobCommand(
            job_id=job.id, actor="t", reason="stale", dry_run=False, stale_after_seconds=60, max_attempts=3
        )
    )
    assert second.outcome == RecoverStaleJobOutcome.RELAUNCHED
    assert second.new_job_id == child.id
    assert worker.idempotent_launches == [(child.id, f"recovery-relaunch:{child.id}")]
    refreshed = job_repo.get_by_id(child.id)
    assert refreshed is not None
    assert refreshed.status == JobStatus.STARTING
    assert refreshed.execution_id == f"exec-relaunch-{child.id}"


def test_second_recovery_not_false_success() -> None:
    uc, job_repo, aisle_repo, inv_repo, worker, _clock, now = _build_uc()
    job, _ = _seed_stale(job_repo=job_repo, aisle_repo=aisle_repo, inv_repo=inv_repo, now=now)
    first = uc.execute(
        RecoverStaleJobCommand(
            job_id=job.id, actor="t", reason="stale", dry_run=False, stale_after_seconds=60, max_attempts=3
        )
    )
    assert first.outcome == RecoverStaleJobOutcome.RECOVERED
    second = uc.execute(
        RecoverStaleJobCommand(
            job_id=job.id, actor="t", reason="stale", dry_run=False, stale_after_seconds=60, max_attempts=3
        )
    )
    assert second.outcome == RecoverStaleJobOutcome.ALREADY_RECOVERED
    assert len(job_repo.list_jobs_by_retry_of(job.id)) == 1
    assert len(worker.launches) == 1


def test_duplicate_relaunch_concurrent() -> None:
    uc, job_repo, aisle_repo, inv_repo, worker, _clock, now = _build_uc()
    parent, child, _aisle = _seed_stale_parent_with_child(
        job_repo=job_repo,
        aisle_repo=aisle_repo,
        inv_repo=inv_repo,
        now=now,
        child_status=JobStatus.FAILED,
        child_failure_code="WORKER_LAUNCH_FAILED",
        parent_stale_failed=True,
    )
    barrier = threading.Barrier(2)
    results: list[Any] = []
    lock = threading.Lock()

    def run() -> None:
        barrier.wait()
        r = uc.execute(
            RecoverStaleJobCommand(
                job_id=parent.id,
                actor="t",
                reason="stale",
                dry_run=False,
                stale_after_seconds=60,
                max_attempts=3,
            )
        )
        with lock:
            results.append(r)

    threads = [threading.Thread(target=run) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    relaunched = [r for r in results if r.outcome == RecoverStaleJobOutcome.RELAUNCHED]
    already = [r for r in results if r.outcome == RecoverStaleJobOutcome.ALREADY_RECOVERED]
    assert len(relaunched) == 1
    assert len(already) == 1
    assert len(worker.idempotent_launches) == 1


def test_child_running_returns_already_recovered() -> None:
    uc, job_repo, aisle_repo, inv_repo, worker, _clock, now = _build_uc()
    parent, child, _aisle = _seed_stale_parent_with_child(
        job_repo=job_repo,
        aisle_repo=aisle_repo,
        inv_repo=inv_repo,
        now=now,
        child_status=JobStatus.RUNNING,
        parent_stale_failed=True,
    )
    result = uc.execute(
        RecoverStaleJobCommand(
            job_id=parent.id, actor="t", reason="stale", dry_run=False, stale_after_seconds=60, max_attempts=3
        )
    )
    assert result.outcome == RecoverStaleJobOutcome.ALREADY_RECOVERED
    assert result.new_job_id == child.id
    assert worker.launches == []
    assert worker.idempotent_launches == []


def test_child_succeeded_returns_already_recovered() -> None:
    uc, job_repo, aisle_repo, inv_repo, worker, _clock, now = _build_uc()
    parent, child, _aisle = _seed_stale_parent_with_child(
        job_repo=job_repo,
        aisle_repo=aisle_repo,
        inv_repo=inv_repo,
        now=now,
        child_status=JobStatus.SUCCEEDED,
        parent_stale_failed=True,
    )
    result = uc.execute(
        RecoverStaleJobCommand(
            job_id=parent.id, actor="t", reason="stale", dry_run=False, stale_after_seconds=60, max_attempts=3
        )
    )
    assert result.outcome == RecoverStaleJobOutcome.ALREADY_RECOVERED
    assert result.detail == "CHILD_SUCCEEDED"
    assert worker.launches == []


def test_child_functional_failure_is_terminal() -> None:
    uc, job_repo, aisle_repo, inv_repo, worker, _clock, now = _build_uc()
    parent, child, _aisle = _seed_stale_parent_with_child(
        job_repo=job_repo,
        aisle_repo=aisle_repo,
        inv_repo=inv_repo,
        now=now,
        child_status=JobStatus.FAILED,
        child_failure_code="PIPELINE_ERROR",
        parent_stale_failed=True,
    )
    result = uc.execute(
        RecoverStaleJobCommand(
            job_id=parent.id, actor="t", reason="stale", dry_run=False, stale_after_seconds=60, max_attempts=3
        )
    )
    assert result.outcome == RecoverStaleJobOutcome.CHILD_TERMINAL
    assert result.new_job_id == child.id
    assert worker.idempotent_launches == []


def test_scheduler_restart_relaunches_launch_failed_child() -> None:
    uc, job_repo, aisle_repo, inv_repo, worker, _clock, now = _build_uc()
    parent, child, _aisle = _seed_stale_parent_with_child(
        job_repo=job_repo,
        aisle_repo=aisle_repo,
        inv_repo=inv_repo,
        now=now,
        child_status=JobStatus.FAILED,
        child_failure_code="WORKER_LAUNCH_FAILED",
        parent_stale_failed=True,
    )
    result = uc.execute(
        RecoverStaleJobCommand(
            job_id=parent.id,
            actor="scheduler",
            reason="automatic_stale_recovery",
            dry_run=False,
            stale_after_seconds=60,
            max_attempts=3,
        )
    )
    assert result.outcome == RecoverStaleJobOutcome.RELAUNCHED
    assert len(worker.idempotent_launches) == 1


def test_relaunch_failure_outcome() -> None:
    uc, job_repo, aisle_repo, inv_repo, worker, _clock, now = _build_uc()
    parent, child, _aisle = _seed_stale_parent_with_child(
        job_repo=job_repo,
        aisle_repo=aisle_repo,
        inv_repo=inv_repo,
        now=now,
        child_status=JobStatus.FAILED,
        child_failure_code="WORKER_LAUNCH_FAILED",
        parent_stale_failed=True,
    )
    worker.relaunch_fail = True
    result = uc.execute(
        RecoverStaleJobCommand(
            job_id=parent.id, actor="t", reason="stale", dry_run=False, stale_after_seconds=60, max_attempts=3
        )
    )
    assert result.outcome == RecoverStaleJobOutcome.RELAUNCH_FAILED
    assert result.new_job_id == child.id
