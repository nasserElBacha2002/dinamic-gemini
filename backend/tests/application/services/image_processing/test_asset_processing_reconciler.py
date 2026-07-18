"""Unit tests for AssetProcessingReconciler (Phase 3 corrections)."""

from __future__ import annotations

from datetime import datetime, timezone

from src.application.ports.manual_image_coverage_repository import ManualImageCoverageLink
from src.application.services.image_processing.asset_processing_reconciler import (
    AssetPersistCompleteness,
    AssetProcessingReconciler,
)
from src.domain.image_processing.job_asset_processing_state import (
    JobAssetProcessingState,
    JobAssetProcessingStatus,
)
from src.infrastructure.repositories.memory_job_asset_processing_state_repository import (
    MemoryJobAssetProcessingStateRepository,
)

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


class FixedClock:
    def now(self) -> datetime:
        return NOW


class FakeCoverageRepo:
    def __init__(self, link: ManualImageCoverageLink | None) -> None:
        self._link = link

    def get_by_job_and_asset(self, job_id: str, source_asset_id: str):
        return self._link

    def save(self, link) -> None:  # pragma: no cover - unused
        raise NotImplementedError

    def list_by_job(self, job_id: str):  # pragma: no cover - unused
        return []


def _link() -> ManualImageCoverageLink:
    return ManualImageCoverageLink(
        id="cov1",
        job_id="job1",
        job_source_asset_id="jsa1",
        source_asset_id="s1",
        position_id="pos-s1",
        aisle_id="a1",
        inventory_id="inv1",
        created_by_user_id=None,
        created_at=NOW,
    )


def _state(status: JobAssetProcessingStatus) -> JobAssetProcessingState:
    return JobAssetProcessingState(
        id="st1",
        job_id="job1",
        asset_id="s1",
        status=status,
        created_at=NOW,
        updated_at=NOW,
        version=1,
    )


def _repo_with(state: JobAssetProcessingState) -> MemoryJobAssetProcessingStateRepository:
    repo = MemoryJobAssetProcessingStateRepository()
    repo.save(state)
    return repo


def test_find_active_result_complete_via_coverage() -> None:
    repo = _repo_with(_state(JobAssetProcessingStatus.PENDING))
    recon = AssetProcessingReconciler(
        state_repo=repo,
        clock=FixedClock(),
        manual_coverage_repo=FakeCoverageRepo(_link()),
    )
    lookup = recon.find_active_result(job_id="job1", asset_id="s1", aisle_id="a1")
    assert lookup.completeness is AssetPersistCompleteness.COMPLETE
    assert lookup.position_id == "pos-s1"


def test_find_active_result_not_found() -> None:
    repo = _repo_with(_state(JobAssetProcessingStatus.PENDING))
    recon = AssetProcessingReconciler(
        state_repo=repo,
        clock=FixedClock(),
        manual_coverage_repo=FakeCoverageRepo(None),
    )
    lookup = recon.find_active_result(job_id="job1", asset_id="s1")
    assert lookup.completeness is AssetPersistCompleteness.NOT_FOUND


def test_reconcile_flips_pending_state_to_resolved_without_scan() -> None:
    state = _state(JobAssetProcessingStatus.PROCESSING)
    repo = _repo_with(state)
    recon = AssetProcessingReconciler(
        state_repo=repo,
        clock=FixedClock(),
        manual_coverage_repo=FakeCoverageRepo(_link()),
    )
    reconciled = recon.reconcile_state_if_complete(state, strategy="CODE_SCAN")
    assert reconciled is True
    saved = repo.get_by_job_and_asset("job1", "s1")
    assert saved.status is JobAssetProcessingStatus.RESOLVED
    assert saved.active_result_id == "pos-s1"


def test_reconcile_noop_when_no_result() -> None:
    state = _state(JobAssetProcessingStatus.PROCESSING)
    repo = _repo_with(state)
    recon = AssetProcessingReconciler(
        state_repo=repo,
        clock=FixedClock(),
        manual_coverage_repo=FakeCoverageRepo(None),
    )
    assert recon.reconcile_state_if_complete(state) is False
    saved = repo.get_by_job_and_asset("job1", "s1")
    assert saved.status is JobAssetProcessingStatus.PROCESSING
