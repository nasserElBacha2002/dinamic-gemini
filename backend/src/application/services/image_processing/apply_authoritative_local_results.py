"""Apply current authoritative local results so remote CODE_SCAN is skipped.

Fail-closed: any structural apply failure raises a typed error; callers must not
fall back to remote CODE_SCAN.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from src.application.errors import (
    AssetProcessingStateConcurrencyError,
    AuthoritativeResultApplyFailedError,
    AuthoritativeResultRepositoryUnavailableError,
    AuthoritativeResultStateConflictError,
)
from src.application.ports.authoritative_local_code_scan_repository import (
    AuthoritativeLocalCodeScanRepository,
)
from src.application.ports.clock import Clock
from src.application.ports.image_processing_repositories import (
    JobAssetProcessingStateRepository,
)
from src.application.services.image_processing.processing_result_persister import (
    PersistSkipReason,
    ProcessingResultPersister,
)
from src.domain.assets.entities import SourceAsset
from src.domain.authoritative_local_code_scan.entities import AuthoritativeLocalCodeScanResult
from src.domain.image_processing.contracts import (
    ExecutionScope,
    ImageProcessingResult,
    ImageResultStatus,
)
from src.domain.image_processing.job_asset_processing_state import (
    JobAssetProcessingState,
    JobAssetProcessingStatus,
)
from src.domain.jobs.entities import Job

logger = logging.getLogger(__name__)

LOCAL_AUTHORITY_STRATEGY = "LOCAL_AUTHORITY"
RESOLVED_BY_LOCAL_AUTHORITY = "RESOLVED_BY_LOCAL_AUTHORITY"


@dataclass(frozen=True)
class ApplyAuthoritativeOutcome:
    applied: int
    already_applied: int
    skipped_no_row: int


class ApplyAuthoritativeLocalResultsService:
    """Persist positions from current authoritative rows and mark assets RESOLVED."""

    def __init__(
        self,
        *,
        authoritative_repo: AuthoritativeLocalCodeScanRepository,
        result_persister: ProcessingResultPersister,
        state_repo: JobAssetProcessingStateRepository,
        clock: Clock,
        enabled: bool,
        require_all_assets: bool = True,
    ) -> None:
        self._repo = authoritative_repo
        self._persister = result_persister
        self._state_repo = state_repo
        self._clock = clock
        self._enabled = enabled
        self._require_all_assets = require_all_assets

    def apply_for_job(
        self,
        *,
        job: Job,
        aisle_id: str,
        inventory_id: str,
        assets: list[SourceAsset],
    ) -> ApplyAuthoritativeOutcome:
        if not self._enabled:
            return ApplyAuthoritativeOutcome(applied=0, already_applied=0, skipped_no_row=0)

        try:
            asset_ids = [a.id for a in assets if a and a.id]
            rows = list(self._repo.list_current_for_asset_ids(asset_ids=asset_ids))
        except Exception as exc:
            raise AuthoritativeResultRepositoryUnavailableError(
                f"Failed to load authoritative results for job_id={job.id}: {type(exc).__name__}"
            ) from exc

        by_asset = {r.asset_id: r for r in rows}
        applied = 0
        already_applied = 0
        skipped_no_row = 0

        for asset in assets:
            row = by_asset.get(asset.id)
            if row is None:
                skipped_no_row += 1
                if self._require_all_assets:
                    raise AuthoritativeResultApplyFailedError(
                        f"Missing authoritative result for asset_id={asset.id}",
                        asset_id=asset.id,
                    )
                continue
            if row.inventory_id != inventory_id or row.aisle_id != aisle_id:
                raise AuthoritativeResultApplyFailedError(
                    f"Authoritative result scope mismatch asset_id={asset.id}",
                    asset_id=asset.id,
                )
            outcome = self._apply_one(job=job, aisle_id=aisle_id, row=row)
            if outcome == "applied":
                applied += 1
            elif outcome == "already":
                already_applied += 1

        logger.info(
            "authoritative_local.apply_batch job_id=%s applied=%s already=%s skipped_no_row=%s",
            job.id,
            applied,
            already_applied,
            skipped_no_row,
        )
        return ApplyAuthoritativeOutcome(
            applied=applied,
            already_applied=already_applied,
            skipped_no_row=skipped_no_row,
        )

    def _apply_one(
        self, *, job: Job, aisle_id: str, row: AuthoritativeLocalCodeScanResult
    ) -> str:
        state = self._state_repo.get_by_job_and_asset(job.id, row.asset_id)

        if state is not None and state.status == JobAssetProcessingStatus.RESOLVED:
            return self._handle_already_resolved(job=job, state=state, row=row)

        result = ImageProcessingResult(
            job_id=job.id,
            asset_id=row.asset_id,
            status=ImageResultStatus.RESOLVED_INTERNAL,
            processing_mode="CODE_SCAN",
            resolved_by=LOCAL_AUTHORITY_STRATEGY,
            internal_code=row.internal_code,
            quantity=row.quantity,
            execution_scope=ExecutionScope.SINGLE_ASSET,
            error_code=RESOLVED_BY_LOCAL_AUTHORITY,
            additional_fields={
                "authoritative_result_id": row.id,
                "authoritative_source": row.source,
                "authoritative_version": row.result_version,
            },
        )
        try:
            outcome = self._persister.persist(
                result=result,
                inventory_id=row.inventory_id,
                aisle_id=aisle_id,
            )
        except Exception as exc:
            raise AuthoritativeResultApplyFailedError(
                f"Position persist failed asset_id={row.asset_id}: {type(exc).__name__}",
                asset_id=row.asset_id,
            ) from exc

        if (
            not outcome.persisted
            and not outcome.reconciled
            and outcome.skipped_reason
            not in {
                PersistSkipReason.ALREADY_PERSISTED,
                PersistSkipReason.MANUAL_RESULT_EXISTS,
            }
        ):
            raise AuthoritativeResultApplyFailedError(
                f"Position persist skipped asset_id={row.asset_id} "
                f"reason={outcome.skipped_reason}",
                asset_id=row.asset_id,
            )

        # MANUAL_RESULT_EXISTS means another authority owns the position — conflict.
        if (
            not outcome.persisted
            and outcome.skipped_reason == PersistSkipReason.MANUAL_RESULT_EXISTS
        ):
            raise AuthoritativeResultStateConflictError(
                f"Manual/remote result already exists for asset_id={row.asset_id}",
                asset_id=row.asset_id,
            )

        if outcome.active_result_id:
            result.additional_fields = {
                **(result.additional_fields or {}),
                "active_result_id": outcome.active_result_id,
            }

        now = self._clock.now()
        if state is None:
            state = self._state_repo.get_by_job_and_asset(job.id, row.asset_id)
        if state is None:
            raise AuthoritativeResultApplyFailedError(
                f"Missing processing state for asset_id={row.asset_id}",
                asset_id=row.asset_id,
            )

        self._finalize_resolved_cas(state, result=result, now=now)
        self._mark_applied_required(row, job.id)

        logger.info(
            "authoritative_local.applied result_id=%s asset_id=%s job_id=%s "
            "version=%s source=%s",
            row.id,
            row.asset_id,
            job.id,
            row.result_version,
            row.source,
        )
        return "applied"

    def _handle_already_resolved(
        self,
        *,
        job: Job,
        state: JobAssetProcessingState,
        row: AuthoritativeLocalCodeScanResult,
    ) -> str:
        """Idempotent only when THIS asset was resolved by local authority for this result."""
        if state.last_strategy == LOCAL_AUTHORITY_STRATEGY and (
            state.error_code == RESOLVED_BY_LOCAL_AUTHORITY
            or (state.active_result_id and row.applied_job_id == job.id)
        ):
            if row.applied_job_id == job.id and row.applied_at is not None:
                return "already"
            # State already LOCAL_AUTHORITY but applied flag missing — complete mark only
            # when we own the resolution.
            if state.last_strategy == LOCAL_AUTHORITY_STRATEGY:
                self._mark_applied_required(row, job.id)
                return "already"

        # Resolved by remote CODE_SCAN / OCR / fallback / manual — not equivalent.
        raise AuthoritativeResultStateConflictError(
            f"Asset already resolved by non-local strategy "
            f"asset_id={row.asset_id} last_strategy={state.last_strategy}",
            asset_id=row.asset_id,
        )

    def _finalize_resolved_cas(
        self,
        state: JobAssetProcessingState,
        *,
        result: ImageProcessingResult,
        now,
    ) -> None:
        expected_version = int(state.version or 1)
        state.status = JobAssetProcessingStatus.RESOLVED
        state.last_strategy = LOCAL_AUTHORITY_STRATEGY
        state.error_code = RESOLVED_BY_LOCAL_AUTHORITY
        state.error_message = None
        state.finished_at = now
        state.updated_at = now
        state.execution_scope = ExecutionScope.SINGLE_ASSET.value
        active = (result.additional_fields or {}).get("active_result_id")
        if active:
            state.active_result_id = str(active)
        state.version = expected_version + 1
        try:
            self._state_repo.save_with_ownership(
                state, expected_version=expected_version, worker_token=None
            )
        except AssetProcessingStateConcurrencyError as exc:
            # Re-read: if already LOCAL_AUTHORITY for this job, treat as success.
            reloaded = self._state_repo.get_by_job_and_asset(state.job_id, state.asset_id)
            if (
                reloaded is not None
                and reloaded.status == JobAssetProcessingStatus.RESOLVED
                and reloaded.last_strategy == LOCAL_AUTHORITY_STRATEGY
            ):
                return
            raise AuthoritativeResultStateConflictError(
                f"State CAS conflict asset_id={state.asset_id}",
                asset_id=state.asset_id,
            ) from exc

    def _mark_applied_required(
        self, row: AuthoritativeLocalCodeScanResult, job_id: str
    ) -> None:
        if row.applied_job_id == job_id and row.applied_at is not None:
            return
        now = self._clock.now()
        updated = self._repo.mark_applied_if_version(
            result_id=row.id,
            job_id=job_id,
            applied_at=now,
            expected_row_version=row.row_version,
        )
        if updated is None:
            # Re-read for idempotent success
            fresh = self._repo.get_by_id(row.id)
            if fresh is not None and fresh.applied_job_id == job_id:
                return
            raise AuthoritativeResultStateConflictError(
                f"mark_applied CAS failed result_id={row.id}",
                asset_id=row.asset_id,
            )
