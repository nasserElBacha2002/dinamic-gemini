"""Apply current authoritative local results so remote CODE_SCAN is skipped."""

from __future__ import annotations

import logging
from dataclasses import dataclass

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
    skipped: int
    errors: tuple[str, ...]


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
    ) -> None:
        self._repo = authoritative_repo
        self._persister = result_persister
        self._state_repo = state_repo
        self._clock = clock
        self._enabled = enabled

    def apply_for_job(
        self,
        *,
        job: Job,
        aisle_id: str,
        inventory_id: str,
        assets: list[SourceAsset],
    ) -> ApplyAuthoritativeOutcome:
        if not self._enabled:
            return ApplyAuthoritativeOutcome(applied=0, skipped=0, errors=())

        asset_ids = [a.id for a in assets if a and a.id]
        rows = list(self._repo.list_current_for_asset_ids(asset_ids=asset_ids))
        by_asset = {r.asset_id: r for r in rows}
        applied = 0
        skipped = 0
        errors: list[str] = []

        for asset in assets:
            row = by_asset.get(asset.id)
            if row is None:
                skipped += 1
                continue
            if row.inventory_id != inventory_id or row.aisle_id != aisle_id:
                errors.append(f"scope_mismatch:{asset.id}")
                continue
            try:
                ok = self._apply_one(job=job, aisle_id=aisle_id, row=row)
            except Exception as exc:  # noqa: BLE001 — isolate per asset
                logger.exception(
                    "authoritative_local.apply_failed job_id=%s asset_id=%s result_id=%s",
                    job.id,
                    asset.id,
                    row.id,
                )
                errors.append(f"apply_failed:{asset.id}:{type(exc).__name__}")
                continue
            if ok:
                applied += 1
            else:
                skipped += 1

        logger.info(
            "authoritative_local.apply_batch job_id=%s applied=%s skipped=%s errors=%s",
            job.id,
            applied,
            skipped,
            len(errors),
        )
        return ApplyAuthoritativeOutcome(
            applied=applied, skipped=skipped, errors=tuple(errors)
        )

    def _apply_one(
        self, *, job: Job, aisle_id: str, row: AuthoritativeLocalCodeScanResult
    ) -> bool:
        state = self._state_repo.get_by_job_and_asset(job.id, row.asset_id)
        if state is not None and state.status == JobAssetProcessingStatus.RESOLVED:
            if row.applied_job_id == job.id:
                return False
            self._mark_applied(row, job.id)
            return False

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
        outcome = self._persister.persist(
            result=result,
            inventory_id=row.inventory_id,
            aisle_id=aisle_id,
        )
        if (
            not outcome.persisted
            and not outcome.reconciled
            and outcome.skipped_reason
            not in {
                PersistSkipReason.ALREADY_PERSISTED,
                PersistSkipReason.MANUAL_RESULT_EXISTS,
            }
        ):
            logger.warning(
                "authoritative_local.persist_skip job_id=%s asset_id=%s reason=%s",
                job.id,
                row.asset_id,
                outcome.skipped_reason,
            )
            return False

        if outcome.active_result_id:
            result.additional_fields = {
                **(result.additional_fields or {}),
                "active_result_id": outcome.active_result_id,
            }

        now = self._clock.now()
        if state is None:
            state = self._state_repo.get_by_job_and_asset(job.id, row.asset_id)
        if state is not None:
            self._finalize_resolved(state, result=result, now=now)

        self._mark_applied(row, job.id)
        logger.info(
            "authoritative_local.applied result_id=%s asset_id=%s job_id=%s "
            "version=%s source=%s",
            row.id,
            row.asset_id,
            job.id,
            row.result_version,
            row.source,
        )
        return True

    def _finalize_resolved(
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
        self._state_repo.save(state)

    def _mark_applied(self, row: AuthoritativeLocalCodeScanResult, job_id: str) -> None:
        if row.applied_job_id == job_id:
            return
        now = self._clock.now()
        self._repo.mark_applied(
            result_id=row.id,
            job_id=job_id,
            applied_at=now,
            expected_row_version=row.row_version,
        )
