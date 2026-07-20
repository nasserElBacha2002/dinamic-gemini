"""Phase 3 corrections — reconcile per-asset state against already-persisted results.

Before (re)scanning an asset, and before recovering an abandoned PROCESSING state back to
PENDING, we must not lose the fact that a *complete* result already exists for
``(job_id, source_asset_id)``. A prior code-scan worker may have persisted a position and
committed the domain rows but crashed before finalizing the ``job_asset_processing_states``
row. Rescanning would either duplicate work or (worse) downgrade a covered asset.

This reconciler is deliberately minimal but real: it looks up existing coverage (the manual
image coverage link — the same uniqueness anchor the persister writes) and, failing that,
valid result-evidence rows for the asset. When a complete result is found it flips the state
to RESOLVED (optimistic version + worker token) without any rescan.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum

from src.application.errors import AssetProcessingStateConcurrencyError
from src.application.ports.clock import Clock
from src.application.ports.image_processing_repositories import (
    JobAssetProcessingStateRepository,
)
from src.application.ports.manual_image_coverage_repository import (
    ManualImageCoverageRepository,
)
from src.application.ports.repositories import ResultEvidenceRepository
from src.domain.image_processing.job_asset_processing_state import (
    JobAssetProcessingState,
    JobAssetProcessingStatus,
)

logger = logging.getLogger(__name__)


class AssetPersistCompleteness(str, Enum):
    COMPLETE = "COMPLETE"
    PARTIAL_REPAIRABLE = "PARTIAL_REPAIRABLE"
    PARTIAL_INVALID = "PARTIAL_INVALID"
    NOT_FOUND = "NOT_FOUND"


@dataclass(frozen=True)
class ActiveResultLookup:
    completeness: AssetPersistCompleteness
    position_id: str | None = None
    active_result_id: str | None = None


class AssetProcessingReconciler:
    def __init__(
        self,
        *,
        state_repo: JobAssetProcessingStateRepository,
        clock: Clock,
        manual_coverage_repo: ManualImageCoverageRepository | None = None,
        result_evidence_repo: ResultEvidenceRepository | None = None,
    ) -> None:
        self._state_repo = state_repo
        self._clock = clock
        self._manual_coverage_repo = manual_coverage_repo
        self._result_evidence_repo = result_evidence_repo

    def find_active_result(
        self, *, job_id: str, asset_id: str, aisle_id: str | None = None
    ) -> ActiveResultLookup:
        """Return whether a persisted result already exists for ``(job_id, asset_id)``."""
        if self._manual_coverage_repo is not None:
            try:
                link = self._manual_coverage_repo.get_by_job_and_asset(job_id, asset_id)
            except Exception:
                logger.warning(
                    "reconciler.coverage_lookup_failed job_id=%s asset_id=%s",
                    job_id,
                    asset_id,
                )
                link = None
            if link is not None and (link.position_id or "").strip():
                return ActiveResultLookup(
                    completeness=AssetPersistCompleteness.COMPLETE,
                    position_id=link.position_id,
                    active_result_id=link.position_id,
                )

        evidence = self._find_result_evidence(job_id, asset_id)
        if evidence is not None:
            if evidence.has_valid_evidence and (evidence.position_id or "").strip():
                return ActiveResultLookup(
                    completeness=AssetPersistCompleteness.COMPLETE,
                    position_id=evidence.position_id,
                    active_result_id=evidence.position_id,
                )
            # Evidence row exists but is not a complete, valid, position-bearing result.
            if (evidence.position_id or "").strip():
                return ActiveResultLookup(
                    completeness=AssetPersistCompleteness.PARTIAL_REPAIRABLE,
                    position_id=evidence.position_id,
                )
            return ActiveResultLookup(completeness=AssetPersistCompleteness.PARTIAL_INVALID)

        return ActiveResultLookup(completeness=AssetPersistCompleteness.NOT_FOUND)

    def _find_result_evidence(self, job_id: str, asset_id: str):
        if self._result_evidence_repo is None:
            return None
        try:
            rows = self._result_evidence_repo.list_by_job_id(job_id)
        except Exception:
            logger.warning(
                "reconciler.result_evidence_lookup_failed job_id=%s asset_id=%s",
                job_id,
                asset_id,
            )
            return None
        for row in rows:
            if (row.source_asset_id or "").strip() == asset_id:
                return row
        return None

    def assess_completeness(
        self, *, job_id: str, asset_id: str, aisle_id: str | None = None
    ) -> AssetPersistCompleteness:
        return self.find_active_result(
            job_id=job_id, asset_id=asset_id, aisle_id=aisle_id
        ).completeness

    def reconcile_state_if_complete(
        self,
        state: JobAssetProcessingState,
        *,
        lookup: ActiveResultLookup | None = None,
        strategy: str | None = None,
        aisle_id: str | None = None,
    ) -> bool:
        """Flip ``state`` to RESOLVED (no rescan) when a complete result already exists.

        Returns True when the state was reconciled to RESOLVED, False otherwise. Uses an
        ownership-checked write so a concurrent finalizer harmlessly wins the race.
        """
        if lookup is None:
            lookup = self.find_active_result(
                job_id=state.job_id, asset_id=state.asset_id, aisle_id=aisle_id
            )
        if lookup.completeness is not AssetPersistCompleteness.COMPLETE:
            return False
        if state.status is JobAssetProcessingStatus.RESOLVED:
            return True

        now = self._clock.now()
        expected_version = int(state.version or 1)
        owner_token = state.worker_token
        state.status = JobAssetProcessingStatus.RESOLVED
        state.active_result_id = lookup.active_result_id or lookup.position_id
        state.finished_at = now
        state.updated_at = now
        state.error_code = None
        state.error_message = None
        if strategy is not None:
            state.last_strategy = strategy
        state.version = expected_version + 1
        try:
            self._state_repo.save_with_ownership(
                state, expected_version=expected_version, worker_token=owner_token
            )
        except AssetProcessingStateConcurrencyError:
            logger.info(
                "reconciler.reconcile_lost_race job_id=%s asset_id=%s",
                state.job_id,
                state.asset_id,
            )
            return False
        logger.info(
            "reconciler.reconciled_to_resolved job_id=%s asset_id=%s position_id=%s",
            state.job_id,
            state.asset_id,
            state.active_result_id,
        )
        return True


__all__ = [
    "ActiveResultLookup",
    "AssetPersistCompleteness",
    "AssetProcessingReconciler",
]
