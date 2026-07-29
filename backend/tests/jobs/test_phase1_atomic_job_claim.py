"""Phase 1 corrections — atomic claim ownership, concurrency, stale reclaim."""

from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from src.application.services.inventory_status_reconciler import InventoryStatusReconciler
from src.application.services.job_stale_reconciler import (
    STALE_FAILURE_CODE,
    JobStaleReconciler,
)
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.assets.entities import SourceAsset, SourceAssetType
from src.domain.inventory.entities import Inventory, InventoryProcessingMode, InventoryStatus
from src.domain.jobs.claim import JobClaimOutcome
from src.domain.jobs.entities import Job, JobStatus
from src.infrastructure.pipeline.v3_job_execution_state import V3JobExecutionStateService
from src.infrastructure.pipeline.v3_job_preparation_service import V3JobPreparationService
from src.infrastructure.repositories.memory_aisle_repository import MemoryAisleRepository
from src.infrastructure.repositories.memory_inventory_repository import MemoryInventoryRepository
from src.infrastructure.repositories.memory_job_repository import MemoryJobRepository
from tests.infrastructure.pipeline.test_v3_job_executor_phase5 import FixedClock


class _FixedClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


def _now() -> datetime:
    return datetime(2026, 7, 28, 12, 0, 0, tzinfo=timezone.utc)


def _job(
    *,
    job_id: str = "job-1",
    status: JobStatus = JobStatus.STARTING,
    execution_id: str | None = "ex-1",
    claim_owner_id: str | None = None,
    attempt_count: int = 1,
    aisle_id: str = "aisle-1",
    heartbeat: datetime | None = None,
) -> Job:
    t = _now()
    return Job(
        id=job_id,
        job_type="process_aisle",
        target_type="aisle",
        target_id=aisle_id,
        status=status,
        payload_json={"aisle_id": aisle_id},
        created_at=t,
        updated_at=t,
        attempt_count=attempt_count,
        execution_id=execution_id,
        claim_owner_id=claim_owner_id,
        last_heartbeat_at=heartbeat or t,
        started_at=t if status != JobStatus.QUEUED else None,
    )


def _aisle(*, status: AisleStatus = AisleStatus.QUEUED, aisle_id: str = "aisle-1") -> Aisle:
    t = _now()
    return Aisle(
        id=aisle_id,
        inventory_id="inv-1",
        code="A1",
        status=status,
        created_at=t,
        updated_at=t,
    )


def _repos():
    aisle_repo = MemoryAisleRepository()
    job_repo = MemoryJobRepository(aisle_repo=aisle_repo)
    return job_repo, aisle_repo


def test_claim_acquired_sets_running_and_aisle_processing():
    job_repo, aisle_repo = _repos()
    job_repo.save(_job())
    aisle_repo.save(_aisle())
    result = job_repo.try_claim_starting_to_running(
        "job-1", now=_now(), claim_owner_id="owner-a", aisle_id="aisle-1"
    )
    assert result.outcome == JobClaimOutcome.ACQUIRED
    assert result.may_execute is True
    assert result.job is not None
    assert result.job.status == JobStatus.RUNNING
    assert result.job.claim_owner_id == "owner-a"
    assert result.job.attempt_count == 1
    assert result.job.current_substep == "startup_confirmed"
    saved_aisle = aisle_repo.get_by_id("aisle-1")
    assert saved_aisle is not None
    assert saved_aisle.status == AisleStatus.PROCESSING


def test_claim_not_found():
    job_repo, _ = _repos()
    result = job_repo.try_claim_starting_to_running(
        "missing", now=_now(), claim_owner_id="owner-a", aisle_id="aisle-1"
    )
    assert result.outcome == JobClaimOutcome.NOT_FOUND
    assert result.may_execute is False


def test_claim_terminal_rejected():
    job_repo, aisle_repo = _repos()
    job_repo.save(_job(status=JobStatus.SUCCEEDED))
    aisle_repo.save(_aisle(status=AisleStatus.PROCESSED))
    result = job_repo.try_claim_starting_to_running(
        "job-1", now=_now(), claim_owner_id="owner-a", aisle_id="aisle-1"
    )
    assert result.outcome == JobClaimOutcome.TERMINAL
    assert result.may_execute is False


def test_claim_idempotent_same_owner_does_not_bump_attempt_or_restart():
    job_repo, aisle_repo = _repos()
    started = _now() - timedelta(minutes=5)
    job = _job(status=JobStatus.RUNNING, claim_owner_id="owner-a")
    job.started_at = started
    job.attempt_count = 3
    job_repo.save(job)
    aisle_repo.save(_aisle(status=AisleStatus.PROCESSING))

    result = job_repo.try_claim_starting_to_running(
        "job-1", now=_now(), claim_owner_id="owner-a", aisle_id="aisle-1"
    )
    assert result.outcome == JobClaimOutcome.ALREADY_OWNED
    assert result.may_execute is True
    refreshed = job_repo.get_by_id("job-1")
    assert refreshed is not None
    assert refreshed.attempt_count == 3
    assert refreshed.started_at == started


def test_same_execution_id_different_claim_owners_conflict():
    job_repo, aisle_repo = _repos()
    job_repo.save(
        _job(status=JobStatus.RUNNING, execution_id="shared-ex", claim_owner_id="owner-a")
    )
    aisle_repo.save(_aisle(status=AisleStatus.PROCESSING))
    result = job_repo.try_claim_starting_to_running(
        "job-1",
        now=_now(),
        claim_owner_id="owner-b",
        aisle_id="aisle-1",
    )
    assert result.outcome == JobClaimOutcome.CONFLICT
    assert result.may_execute is False


def test_null_caller_claim_owner_never_owns():
    job_repo, aisle_repo = _repos()
    job_repo.save(_job(status=JobStatus.RUNNING, claim_owner_id="owner-a"))
    aisle_repo.save(_aisle(status=AisleStatus.PROCESSING))
    result = job_repo.try_claim_starting_to_running(
        "job-1", now=_now(), claim_owner_id="", aisle_id="aisle-1"
    )
    assert result.outcome == JobClaimOutcome.CONFLICT
    assert result.may_execute is False


def test_null_persisted_claim_owner_is_conflict():
    job_repo, aisle_repo = _repos()
    job_repo.save(_job(status=JobStatus.RUNNING, claim_owner_id=None))
    aisle_repo.save(_aisle(status=AisleStatus.PROCESSING))
    result = job_repo.try_claim_starting_to_running(
        "job-1", now=_now(), claim_owner_id="owner-a", aisle_id="aisle-1"
    )
    assert result.outcome == JobClaimOutcome.CONFLICT
    assert result.may_execute is False


def test_both_null_claim_owners_conflict():
    job_repo, aisle_repo = _repos()
    job_repo.save(_job(status=JobStatus.RUNNING, claim_owner_id=None))
    aisle_repo.save(_aisle(status=AisleStatus.PROCESSING))
    result = job_repo.try_claim_starting_to_running(
        "job-1", now=_now(), claim_owner_id="  ", aisle_id="aisle-1"
    )
    assert result.outcome == JobClaimOutcome.CONFLICT
    assert result.may_execute is False


def test_two_workers_one_acquired_one_conflict():
    job_repo, aisle_repo = _repos()
    job_repo.save(_job(execution_id="shared-ex"))
    aisle_repo.save(_aisle())
    barrier = threading.Barrier(2)
    outcomes: list[JobClaimOutcome] = []
    may_flags: list[bool] = []
    lock = threading.Lock()

    def worker(owner: str) -> None:
        barrier.wait()
        result = job_repo.try_claim_starting_to_running(
            "job-1",
            now=_now(),
            claim_owner_id=owner,
            aisle_id="aisle-1",
        )
        with lock:
            outcomes.append(result.outcome)
            may_flags.append(result.may_execute)

    t1 = threading.Thread(target=worker, args=("owner-a",))
    t2 = threading.Thread(target=worker, args=("owner-b",))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert outcomes.count(JobClaimOutcome.ACQUIRED) == 1
    assert outcomes.count(JobClaimOutcome.CONFLICT) == 1
    assert outcomes.count(JobClaimOutcome.ALREADY_OWNED) == 0
    assert may_flags.count(True) == 1
    final = job_repo.get_by_id("job-1")
    assert final is not None
    assert final.status == JobStatus.RUNNING
    assert final.attempt_count == 1
    assert aisle_repo.get_by_id("aisle-1").status == AisleStatus.PROCESSING


def test_eight_workers_single_authorized():
    job_repo, aisle_repo = _repos()
    job_repo.save(_job(execution_id="shared-ex"))
    aisle_repo.save(_aisle())
    n = 8
    barrier = threading.Barrier(n)
    outcomes: list[JobClaimOutcome] = []
    may_flags: list[bool] = []
    lock = threading.Lock()

    def worker(i: int) -> None:
        barrier.wait()
        result = job_repo.try_claim_starting_to_running(
            "job-1",
            now=_now(),
            claim_owner_id=f"owner-{i}",
            aisle_id="aisle-1",
        )
        with lock:
            outcomes.append(result.outcome)
            may_flags.append(result.may_execute)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert outcomes.count(JobClaimOutcome.ACQUIRED) == 1
    assert outcomes.count(JobClaimOutcome.ALREADY_OWNED) == 0
    assert may_flags.count(True) == 1
    assert len(outcomes) == n
    assert job_repo.get_by_id("job-1").status == JobStatus.RUNNING


def test_claim_aisle_missing():
    job_repo, _ = _repos()
    job_repo.save(_job())
    result = job_repo.try_claim_starting_to_running(
        "job-1", now=_now(), claim_owner_id="owner-a", aisle_id="aisle-1"
    )
    assert result.outcome == JobClaimOutcome.TARGET_NOT_FOUND
    assert result.may_execute is False
    assert job_repo.get_by_id("job-1").status == JobStatus.STARTING


def test_claim_aisle_terminal():
    job_repo, aisle_repo = _repos()
    job_repo.save(_job())
    aisle_repo.save(_aisle(status=AisleStatus.FAILED))
    result = job_repo.try_claim_starting_to_running(
        "job-1", now=_now(), claim_owner_id="owner-a", aisle_id="aisle-1"
    )
    assert result.outcome == JobClaimOutcome.TARGET_INVALID_STATUS
    assert result.may_execute is False
    assert job_repo.get_by_id("job-1").status == JobStatus.STARTING
    assert aisle_repo.get_by_id("aisle-1").status == AisleStatus.FAILED


def test_claim_target_mismatch():
    job_repo, aisle_repo = _repos()
    job_repo.save(_job(aisle_id="aisle-1"))
    aisle_repo.save(_aisle(aisle_id="aisle-2"))
    result = job_repo.try_claim_starting_to_running(
        "job-1", now=_now(), claim_owner_id="owner-a", aisle_id="aisle-2"
    )
    assert result.outcome == JobClaimOutcome.TARGET_MISMATCH
    assert result.may_execute is False
    assert job_repo.get_by_id("job-1").status == JobStatus.STARTING


def test_claim_next_queued_mutates_to_starting():
    job_repo, _ = _repos()
    job_repo.save(_job(status=JobStatus.QUEUED, execution_id="ex-q"))
    claimed = job_repo.claim_next_queued_job()
    assert claimed is not None
    assert claimed.status == JobStatus.STARTING
    again = job_repo.claim_next_queued_job()
    assert again is None


def test_stale_reclaim_fails_job_and_aisle():
    job_repo, aisle_repo = _repos()
    old = _now() - timedelta(hours=2)
    job = _job(status=JobStatus.RUNNING, heartbeat=old, claim_owner_id="owner-a")
    job.updated_at = old
    job_repo.save(job)
    aisle_repo.save(_aisle(status=AisleStatus.PROCESSING))

    count = job_repo.reclaim_stale_running_jobs(stale_after_seconds=60)
    assert count == 1
    refreshed = job_repo.get_by_id("job-1")
    assert refreshed is not None
    assert refreshed.status == JobStatus.FAILED
    assert refreshed.failure_code == STALE_FAILURE_CODE
    assert aisle_repo.get_by_id("aisle-1").status == AisleStatus.FAILED


def test_stale_reclaim_skips_fresh_heartbeat():
    job_repo, aisle_repo = _repos()
    fresh = datetime.now(timezone.utc)
    job = _job(status=JobStatus.RUNNING, heartbeat=fresh)
    job.updated_at = fresh
    job_repo.save(job)
    aisle_repo.save(_aisle(status=AisleStatus.PROCESSING))
    assert job_repo.reclaim_stale_running_jobs(stale_after_seconds=60) == 0
    assert job_repo.get_by_id("job-1").status == JobStatus.RUNNING


def test_stale_reclaim_does_not_fail_aisle_when_other_active_job():
    job_repo, aisle_repo = _repos()
    old = _now() - timedelta(hours=2)
    stale = _job(
        job_id="job-stale",
        status=JobStatus.RUNNING,
        heartbeat=old,
        execution_id="ex-s",
        claim_owner_id="owner-s",
    )
    stale.updated_at = old
    active = _job(
        job_id="job-active",
        status=JobStatus.RUNNING,
        execution_id="ex-a",
        claim_owner_id="owner-a",
    )
    job_repo.save(stale)
    job_repo.save(active)
    aisle_repo.save(_aisle(status=AisleStatus.PROCESSING))

    result = job_repo.try_reclaim_stale_job_and_reconcile_aisle(
        "job-stale", now=_now(), stale_after_seconds=60
    )
    assert result.won is True
    assert result.aisle_transition_applied is False
    assert aisle_repo.get_by_id("aisle-1").status == AisleStatus.PROCESSING
    assert job_repo.get_by_id("job-stale").status == JobStatus.FAILED


def test_two_recovery_workers_one_stale_reclaim():
    job_repo, aisle_repo = _repos()
    old = _now() - timedelta(hours=2)
    job = _job(status=JobStatus.RUNNING, heartbeat=old)
    job.updated_at = old
    job_repo.save(job)
    aisle_repo.save(_aisle(status=AisleStatus.PROCESSING))
    barrier = threading.Barrier(2)
    wins: list[bool] = []
    lock = threading.Lock()

    def recovery() -> None:
        barrier.wait()
        result = job_repo.try_reclaim_stale_job_and_reconcile_aisle(
            "job-1", now=_now(), stale_after_seconds=60
        )
        with lock:
            wins.append(result.won)

    threads = [threading.Thread(target=recovery) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert wins.count(True) == 1
    assert wins.count(False) == 1


def test_mark_running_different_owners_only_one_may_execute():
    now = _now()
    aisle_repo = MemoryAisleRepository()
    job_repo = MemoryJobRepository(aisle_repo=aisle_repo)
    inv = Inventory(
        id="inv-1",
        name="Inv",
        status=InventoryStatus.PROCESSING,
        created_at=now,
        updated_at=now,
        processing_mode=InventoryProcessingMode.TEST,
    )
    inventory_repo = MemoryInventoryRepository()
    inventory_repo.save(inv)
    svc = V3JobExecutionStateService(
        job_repo=job_repo,
        aisle_repo=aisle_repo,
        inventory_repo=inventory_repo,
        clock=_FixedClock(now),
        inventory_status_reconciler=MagicMock(spec=InventoryStatusReconciler),
    )
    job_repo.save(_job(execution_id="shared-ex"))
    aisle = _aisle()
    aisle_repo.save(aisle)

    first = svc.mark_running("job-1", aisle, now, claim_owner_id="owner-a")
    second = svc.mark_running("job-1", aisle, now, claim_owner_id="owner-b")
    assert first.outcome == JobClaimOutcome.ACQUIRED
    assert first.may_execute is True
    assert second.outcome == JobClaimOutcome.CONFLICT
    assert second.may_execute is False

    same = svc.mark_running("job-1", aisle, now, claim_owner_id="owner-a")
    assert same.outcome == JobClaimOutcome.ALREADY_OWNED
    assert same.may_execute is True


def test_preparation_side_effect_single_pipeline_authorization():
    """Two workers through real preparation: only one continues to pipeline."""
    now = _now()
    aisle_repo = MemoryAisleRepository()
    job_repo = MemoryJobRepository(aisle_repo=aisle_repo)
    inv_repo = MemoryInventoryRepository()
    inv_repo.save(
        Inventory(
            id="inv-1",
            name="Inv",
            status=InventoryStatus.PROCESSING,
            created_at=now,
            updated_at=now,
            processing_mode=InventoryProcessingMode.TEST,
        )
    )
    job_repo.save(_job(execution_id="shared-ex"))
    aisle_repo.save(_aisle(status=AisleStatus.QUEUED))

    class _Assets:
        def list_by_aisle(self, aid: str):
            return [
                SourceAsset(
                    id="a1",
                    aisle_id=aid,
                    type=SourceAssetType.PHOTO,
                    original_filename="p.jpg",
                    storage_path="p.jpg",
                    mime_type="image/jpeg",
                    uploaded_at=now,
                )
            ]

    state = V3JobExecutionStateService(
        job_repo=job_repo,
        aisle_repo=aisle_repo,
        inventory_repo=inv_repo,
        clock=_FixedClock(now),
        inventory_status_reconciler=MagicMock(spec=InventoryStatusReconciler),
    )
    prep = V3JobPreparationService(
        job_repo=job_repo,
        aisle_repo=aisle_repo,
        source_asset_repo=_Assets(),
        state_service=state,
        clock=FixedClock(now),
    )
    barrier = threading.Barrier(2)
    continues: list[bool] = []
    lock = threading.Lock()

    def worker() -> None:
        barrier.wait()
        result = prep.prepare("job-1")
        with lock:
            continues.append(result.stop is False and result.prepared is not None)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert continues.count(True) == 1
    assert continues.count(False) == 1
    assert job_repo.get_by_id("job-1").status == JobStatus.RUNNING
    assert job_repo.get_by_id("job-1").status != JobStatus.FAILED


def test_job_stale_reconciler_uses_atomic_reclaim():
    now = _now()
    aisle_repo = MemoryAisleRepository()
    job_repo = MemoryJobRepository(aisle_repo=aisle_repo)
    old = now - timedelta(hours=1)
    job = _job(status=JobStatus.RUNNING, heartbeat=old, claim_owner_id="owner-a")
    job.updated_at = old
    job_repo.save(job)
    aisle_repo.save(_aisle(status=AisleStatus.PROCESSING))
    reconciler = JobStaleReconciler(
        job_repo=job_repo,
        clock=_FixedClock(now),
        stale_after_seconds=30,
        aisle_repo=aisle_repo,
    )
    out = reconciler.reconcile(job)
    assert out is not None
    assert out.status == JobStatus.FAILED
    assert aisle_repo.get_by_id("aisle-1").status == AisleStatus.FAILED
