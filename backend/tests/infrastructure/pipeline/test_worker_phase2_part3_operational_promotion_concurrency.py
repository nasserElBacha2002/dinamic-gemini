"""Phase 2 Part 3 — operational promotion, concurrency, cleanup (P2-P3-T001–T013)."""

from __future__ import annotations

import threading
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from src.application.ports.job_result_unit_of_work import JobResultRepositories
from src.application.ports.operational_job_promotion import PromotionOutcome
from src.application.services.export_inventory_collector import ExportInventoryCollector
from src.application.services.inventory_status_reconciler import InventoryStatusReconciler
from src.application.services.result_context_resolver import (
    ResultContextResolver,
    ResultReadMode,
)
from src.application.use_cases.aisles.list_aisles_with_status import ListAislesWithStatusUseCase
from src.application.use_cases.pipeline.cleanup_job_results import (
    CleanupJobResultsCommand,
    CleanupJobResultsOutcome,
    CleanupJobResultsUseCase,
)
from src.application.use_cases.pipeline.persist_aisle_result import PersistAisleResultCommand
from src.application.use_cases.positions.list_aisle_positions import (
    ListAislePositionsCommand,
    ListAislePositionsUseCase,
)
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.inventory.entities import Inventory, InventoryProcessingMode, InventoryStatus
from src.domain.jobs.entities import Job, JobStatus
from src.infrastructure.persistence.memory_job_result_unit_of_work import (
    MemoryJobResultUnitOfWorkFactory,
)
from src.infrastructure.pipeline.v3_job_execution_state import V3JobExecutionStateService
from src.infrastructure.repositories.memory_result_evidence_repository import (
    MemoryResultEvidenceRepository,
)
from tests.support.worker_phase1.executor_harness import (
    ExecutorHarness,
    FixedClock,
    make_two_entity_hybrid_report,
)
from tests.support.worker_phase2.promotion_builders import build_operational_promotion_service


def _ts(base: datetime, minutes: int) -> datetime:
    return base + timedelta(minutes=minutes)


def _save_job(
    harness: ExecutorHarness,
    *,
    job_id: str,
    status: JobStatus,
    created_at: datetime,
    aisle_id: str | None = None,
) -> Job:
    aid = aisle_id or harness.aisle_id
    job = Job(
        id=job_id,
        target_type="aisle",
        target_id=aid,
        job_type="process_aisle",
        status=status,
        payload_json={"aisle_id": aid},
        created_at=created_at,
        updated_at=created_at,
    )
    harness.job_repo.save(job)
    return job


def _state_service(harness: ExecutorHarness) -> V3JobExecutionStateService:
    clock = FixedClock(harness.now)
    reconciler = InventoryStatusReconciler(
        harness.inventory_repo, harness.aisle_repo, clock
    )
    return V3JobExecutionStateService(
        job_repo=harness.job_repo,
        aisle_repo=harness.aisle_repo,
        inventory_repo=harness.inventory_repo,
        clock=clock,
        inventory_status_reconciler=reconciler,
        operational_promotion_service=build_operational_promotion_service(harness),
    )


def _cleanup_uc(harness: ExecutorHarness) -> CleanupJobResultsUseCase:
    repos = JobResultRepositories(
        position_repo=harness.position_repo,
        product_record_repo=harness.product_repo,
        evidence_repo=harness.evidence_repo,
        raw_label_repo=harness.raw_repo,
        normalized_label_repo=harness.norm_repo,
        final_count_repo=harness.final_repo,
        result_evidence_repo=MemoryResultEvidenceRepository(),
    )
    return CleanupJobResultsUseCase(
        aisle_repo=harness.aisle_repo,
        job_repo=harness.job_repo,
        job_result_uow_factory=MemoryJobResultUnitOfWorkFactory(),
        repositories=repos,
    )


@pytest.mark.parametrize(
    "status",
    [
        JobStatus.STARTING,
        JobStatus.RUNNING,
        JobStatus.CANCEL_REQUESTED,
        JobStatus.CANCELED,
        JobStatus.FAILED,
    ],
)
def test_p2_p3_t001_invalid_status_cannot_promote(tmp_path: Path, status: JobStatus) -> None:
    harness = ExecutorHarness.build(tmp_path)
    harness.inventory_repo.save(
        Inventory(
            harness.inventory_id,
            "P3",
            InventoryStatus.PROCESSING,
            harness.now,
            harness.now,
            processing_mode=InventoryProcessingMode.PRODUCTION,
        )
    )
    _save_job(harness, job_id="j-bad", status=status, created_at=harness.now)
    promo = build_operational_promotion_service(harness)
    result = promo.promote_for_success(aisle_id=harness.aisle_id, candidate_job_id="j-bad")
    assert result.outcome == PromotionOutcome.REJECTED_INVALID_STATUS


def test_p2_p3_t001_succeeded_can_promote(tmp_path: Path) -> None:
    harness = ExecutorHarness.build(tmp_path)
    harness.inventory_repo.save(
        Inventory(
            harness.inventory_id,
            "P3",
            InventoryStatus.PROCESSING,
            harness.now,
            harness.now,
            processing_mode=InventoryProcessingMode.PRODUCTION,
        )
    )
    _save_job(harness, job_id="j-ok", status=JobStatus.SUCCEEDED, created_at=harness.now)
    promo = build_operational_promotion_service(harness)
    result = promo.promote_for_success(aisle_id=harness.aisle_id, candidate_job_id="j-ok")
    assert result.outcome == PromotionOutcome.PROMOTED
    assert harness.aisle_repo.get_by_id(harness.aisle_id).operational_job_id == "j-ok"


def test_p2_p3_t002_wrong_aisle_cannot_promote(tmp_path: Path) -> None:
    harness = ExecutorHarness.build(tmp_path)
    other_aisle = "aisle-other"
    harness.aisle_repo.save(
        Aisle(other_aisle, harness.inventory_id, "O", AisleStatus.PROCESSING, harness.now, harness.now)
    )
    _save_job(harness, job_id="j-wrong", status=JobStatus.SUCCEEDED, created_at=harness.now, aisle_id=other_aisle)
    promo = build_operational_promotion_service(harness)
    result = promo.promote_for_success(aisle_id=harness.aisle_id, candidate_job_id="j-wrong")
    assert result.outcome == PromotionOutcome.REJECTED_WRONG_AISLE


def test_p2_p3_t003_older_job_cannot_overwrite_newer_operational(tmp_path: Path) -> None:
    harness = ExecutorHarness.build(tmp_path)
    base = harness.now
    harness.inventory_repo.save(
        Inventory(
            harness.inventory_id,
            "P3",
            InventoryStatus.PROCESSING,
            base,
            base,
            processing_mode=InventoryProcessingMode.PRODUCTION,
        )
    )
    _save_job(harness, job_id="job-1", status=JobStatus.SUCCEEDED, created_at=_ts(base, 0))
    _save_job(harness, job_id="job-2", status=JobStatus.SUCCEEDED, created_at=_ts(base, 10))
    promo = build_operational_promotion_service(harness)
    assert promo.promote_for_success(aisle_id=harness.aisle_id, candidate_job_id="job-2").outcome == PromotionOutcome.PROMOTED
    stale = promo.promote_for_success(aisle_id=harness.aisle_id, candidate_job_id="job-1")
    assert stale.outcome == PromotionOutcome.REJECTED_STALE
    assert harness.aisle_repo.get_by_id(harness.aisle_id).operational_job_id == "job-2"


def test_p2_p3_t004_newer_job_replaces_older_operational(tmp_path: Path) -> None:
    harness = ExecutorHarness.build(tmp_path)
    base = harness.now
    harness.inventory_repo.save(
        Inventory(
            harness.inventory_id,
            "P3",
            InventoryStatus.PROCESSING,
            base,
            base,
            processing_mode=InventoryProcessingMode.PRODUCTION,
        )
    )
    _save_job(harness, job_id="job-1", status=JobStatus.SUCCEEDED, created_at=_ts(base, 0))
    _save_job(harness, job_id="job-2", status=JobStatus.SUCCEEDED, created_at=_ts(base, 5))
    promo = build_operational_promotion_service(harness)
    promo.promote_for_success(aisle_id=harness.aisle_id, candidate_job_id="job-1")
    result = promo.promote_for_success(aisle_id=harness.aisle_id, candidate_job_id="job-2")
    assert result.outcome == PromotionOutcome.PROMOTED
    assert harness.aisle_repo.get_by_id(harness.aisle_id).operational_job_id == "job-2"


def test_p2_p3_t005_concurrent_promotion_has_one_winner(tmp_path: Path) -> None:
    harness = ExecutorHarness.build(tmp_path)
    base = harness.now
    harness.inventory_repo.save(
        Inventory(
            harness.inventory_id,
            "P3",
            InventoryStatus.PROCESSING,
            base,
            base,
            processing_mode=InventoryProcessingMode.PRODUCTION,
        )
    )
    _save_job(harness, job_id="job-a", status=JobStatus.SUCCEEDED, created_at=_ts(base, 0))
    _save_job(harness, job_id="job-b", status=JobStatus.SUCCEEDED, created_at=_ts(base, 10))
    promo = build_operational_promotion_service(harness)
    barrier = threading.Barrier(2)
    results: list = []

    def _promote(jid: str) -> None:
        barrier.wait()
        results.append(promo.promote_for_success(aisle_id=harness.aisle_id, candidate_job_id=jid))

    t1 = threading.Thread(target=_promote, args=("job-a",))
    t2 = threading.Thread(target=_promote, args=("job-b",))
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    outcomes = {r.outcome for r in results}
    assert PromotionOutcome.PROMOTED in outcomes
    assert harness.aisle_repo.get_by_id(harness.aisle_id).operational_job_id == "job-b"


def test_p2_p3_t006_stale_successful_job_remains_succeeded(tmp_path: Path) -> None:
    harness = ExecutorHarness.build(tmp_path)
    base = harness.now
    harness.inventory_repo.save(
        Inventory(
            harness.inventory_id,
            "P3",
            InventoryStatus.PROCESSING,
            base,
            base,
            processing_mode=InventoryProcessingMode.PRODUCTION,
        )
    )
    _save_job(harness, job_id="job-new", status=JobStatus.SUCCEEDED, created_at=_ts(base, 10))
    _save_job(harness, job_id="job-old", status=JobStatus.RUNNING, created_at=_ts(base, 0))
    state = _state_service(harness)
    aisle = harness.aisle_repo.get_by_id(harness.aisle_id)
    assert aisle is not None
    state.mark_success("job-new", aisle, Path("/tmp/r.json"))
    aisle = harness.aisle_repo.get_by_id(harness.aisle_id)
    assert aisle is not None
    job_old = harness.job_repo.get_by_id("job-old")
    assert job_old is not None
    job_old.status = JobStatus.SUCCEEDED
    harness.job_repo.save(job_old)
    state.mark_success("job-old", aisle, Path("/tmp/r2.json"))
    assert harness.job_repo.get_by_id("job-old").status == JobStatus.SUCCEEDED
    assert harness.aisle_repo.get_by_id(harness.aisle_id).operational_job_id == "job-new"


def test_p2_p3_t007_late_failure_handler_does_not_downgrade_newer_result(tmp_path: Path) -> None:
    harness = ExecutorHarness.build(tmp_path)
    base = harness.now
    harness.inventory_repo.save(
        Inventory(
            harness.inventory_id,
            "P3",
            InventoryStatus.PROCESSING,
            base,
            base,
            processing_mode=InventoryProcessingMode.PRODUCTION,
        )
    )
    _save_job(harness, job_id="job-new", status=JobStatus.SUCCEEDED, created_at=_ts(base, 10))
    _save_job(harness, job_id="job-old", status=JobStatus.RUNNING, created_at=_ts(base, 0))
    state = _state_service(harness)
    aisle = harness.aisle_repo.get_by_id(harness.aisle_id)
    assert aisle is not None
    state.mark_success("job-new", aisle, Path("/tmp/r.json"))
    aisle = harness.aisle_repo.get_by_id(harness.aisle_id)
    assert aisle is not None
    assert aisle.status == AisleStatus.PROCESSED
    state.fail_job_and_aisle("job-old", aisle, "late failure")
    refreshed = harness.aisle_repo.get_by_id(harness.aisle_id)
    assert refreshed is not None
    assert refreshed.operational_job_id == "job-new"
    assert refreshed.status == AisleStatus.PROCESSED


def test_p2_p3_t008_operational_cleanup_rejected(tmp_path: Path) -> None:
    harness = ExecutorHarness.build(tmp_path)
    harness.persist_report(make_two_entity_hybrid_report())
    aisle = harness.aisle_repo.get_by_id(harness.aisle_id)
    assert aisle is not None
    aisle.operational_job_id = harness.job_id
    harness.aisle_repo.save(aisle)
    result = _cleanup_uc(harness).execute(
        CleanupJobResultsCommand(
            inventory_id=harness.inventory_id,
            aisle_id=harness.aisle_id,
            job_id=harness.job_id,
            reason="test",
        )
    )
    assert result.outcome == CleanupJobResultsOutcome.REJECTED_OPERATIONAL_JOB
    assert len(harness.positions_for_job()) == 2


def test_p2_p3_t009_non_operational_failed_job_cleanup(tmp_path: Path) -> None:
    harness = ExecutorHarness.build(tmp_path, job_id="job-failed")
    harness.persist_report(make_two_entity_hybrid_report())
    _save_job(harness, job_id="job-op", status=JobStatus.SUCCEEDED, created_at=_ts(harness.now, 5))
    aisle = harness.aisle_repo.get_by_id(harness.aisle_id)
    assert aisle is not None
    aisle.operational_job_id = "job-op"
    harness.aisle_repo.save(aisle)
    _save_job(harness, job_id="job-failed", status=JobStatus.FAILED, created_at=harness.now)
    result = _cleanup_uc(harness).execute(
        CleanupJobResultsCommand(
            inventory_id=harness.inventory_id,
            aisle_id=harness.aisle_id,
            job_id="job-failed",
            reason="test",
        )
    )
    assert result.outcome == CleanupJobResultsOutcome.CLEANED
    assert len(harness.positions_for_job("job-failed")) == 0
    assert harness.aisle_repo.get_by_id(harness.aisle_id).operational_job_id == "job-op"


def test_p2_p3_t010_active_job_cleanup_rejected(tmp_path: Path) -> None:
    harness = ExecutorHarness.build(tmp_path)
    cleanup = _cleanup_uc(harness)
    for status in (JobStatus.STARTING, JobStatus.RUNNING, JobStatus.CANCEL_REQUESTED):
        jid = f"job-{status.value}"
        _save_job(harness, job_id=jid, status=status, created_at=harness.now)
        result = cleanup.execute(
            CleanupJobResultsCommand(
                inventory_id=harness.inventory_id,
                aisle_id=harness.aisle_id,
                job_id=jid,
            )
        )
        assert result.outcome == CleanupJobResultsOutcome.REJECTED_ACTIVE_JOB


def test_p2_p3_t011_operational_readers_agree(tmp_path: Path) -> None:
    harness = ExecutorHarness.build(tmp_path)
    harness.persist_report(make_two_entity_hybrid_report())
    _save_job(harness, job_id="job-other", status=JobStatus.SUCCEEDED, created_at=_ts(harness.now, 5))
    aisle = harness.aisle_repo.get_by_id(harness.aisle_id)
    assert aisle is not None
    aisle.operational_job_id = harness.job_id
    harness.aisle_repo.save(aisle)
    resolver = ResultContextResolver(harness.job_repo, harness.position_repo)
    ctx = resolver.resolve(aisle=aisle, explicit_job_id=None)
    list_uc = ListAislePositionsUseCase(
        harness.inventory_repo,
        harness.aisle_repo,
        harness.position_repo,
        resolver,
        harness.product_repo,
        positions_aisle_raw_cap=500,
    )
    positions = list_uc.execute(
        ListAislePositionsCommand(
            inventory_id=harness.inventory_id,
            aisle_id=harness.aisle_id,
            page=1,
            page_size=50,
        )
    )
    export_slice = ExportInventoryCollector(
        harness.inventory_repo,
        harness.aisle_repo,
        harness.position_repo,
        harness.product_repo,
        resolver,
    ).collect_inventory(harness.inventory_id)
    list_aisles = ListAislesWithStatusUseCase(
        harness.inventory_repo,
        harness.aisle_repo,
        harness.job_repo,
        harness.position_repo,
        harness.source_asset_repo,
        resolver,
    ).execute(harness.inventory_id)[0]
    row = next(r for r in list_aisles if r.aisle.id == harness.aisle_id)
    bundle = next(b for b in export_slice.aisle_bundles if b.aisle.id == harness.aisle_id)
    assert ctx.job_id_for_slice == harness.job_id
    assert bundle.job_id_for_slice == harness.job_id
    assert all(p.job_id == harness.job_id for p in positions.positions)
    assert len(bundle.rows) == 2
    assert row.positions_count == 2


def test_p2_p3_t012_explicit_audit_all_remains_available(tmp_path: Path) -> None:
    harness = ExecutorHarness.build(tmp_path)
    resolver = ResultContextResolver(harness.job_repo)
    aisle = harness.aisle_repo.get_by_id(harness.aisle_id)
    assert aisle is not None
    ctx = resolver.resolve(aisle=aisle, explicit_job_id=None, read_mode=ResultReadMode.AUDIT_ALL)
    assert ctx.read_mode == ResultReadMode.AUDIT_ALL
    assert ctx.job_id_for_slice == "all"
    assert ctx.source == "audit_all"


def test_p2_p3_t013_no_default_all_operational_scope(tmp_path: Path) -> None:
    harness = ExecutorHarness.build(tmp_path)
    persist = harness.make_persist_use_case()
    with pytest.raises(ValueError, match="rejects broad job_id scope"):
        persist.execute(
            PersistAisleResultCommand(
                aisle_id=harness.aisle_id,
                job_id="all",
                report=make_two_entity_hybrid_report(),
                run_dir=tmp_path,
            )
        )
