"""Apply GLOBAL_BATCH merge plan idempotently (no planning side effects)."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from src.application.ports.global_fallback_batch_request_repository import (
    GlobalFallbackBatchRequestRepository,
)
from src.application.services.image_processing.external_fallback_mode import (
    EXTERNAL_FALLBACK_MODE_GLOBAL_BATCH,
    GLOBAL_FALLBACK_ANALYSIS_CONTRACT,
    GLOBAL_FALLBACK_SCHEMA_VERSION,
)
from src.application.services.image_processing.global_fallback_merge_planner import (
    GlobalFallbackMergePlan,
)
from src.domain.assets.entities import SourceAsset
from src.domain.image_processing.contracts import (
    ExecutionScope,
    ImageProcessingResult,
    ImageResultStatus,
)
from src.domain.image_processing.global_fallback_batch_request import (
    GlobalFallbackBatchRequest,
    GlobalFallbackBatchStatus,
)
from src.domain.image_processing.job_asset_processing_state import (
    JobAssetProcessingStatus,
)

logger = logging.getLogger(__name__)

EXTERNAL_PROVIDER_STRATEGY = "EXTERNAL_PROVIDER"
EXTERNAL_CODE_MISSING_QUANTITY_REASON = "external_code_missing_quantity"


@dataclass
class GlobalFallbackMergeApplyResult:
    applied: int = 0
    skipped_idempotent: int = 0
    conflicts_marked: int = 0
    failed: bool = False
    error_code: str | None = None
    error_message: str | None = None


class GlobalFallbackMergeApplier:
    def __init__(
        self,
        *,
        result_persister: Any,
        batch_journal: GlobalFallbackBatchRequestRepository,
        state_repo: Any | None = None,
        clock: Any | None = None,
    ) -> None:
        self._persister = result_persister
        self._journal = batch_journal
        self._state_repo = state_repo
        self._clock = clock

    def apply(
        self,
        *,
        job: Any,
        aisle: Any,
        asset_by_id: Mapping[str, SourceAsset],
        plan: GlobalFallbackMergePlan,
        batch_row: GlobalFallbackBatchRequest,
        snapshot: Any,
    ) -> GlobalFallbackMergeApplyResult:
        result = GlobalFallbackMergeApplyResult()
        batch_row.status = GlobalFallbackBatchStatus.PERSISTING
        batch_row.merge_plan_json = plan.to_public_dict()
        batch_row.updated_at = self._now()
        self._journal.save(batch_row)

        try:
            for op in plan.operations:
                appended = self._journal.append_applied_operation_key(
                    batch_row.id, operation_key=op.idempotency_key
                )
                if not appended:
                    result.skipped_idempotent += 1
                    continue
                decision = op.decision
                if decision.asset_id is None or decision.external is None:
                    continue
                asset = asset_by_id.get(decision.asset_id)
                if asset is None:
                    continue
                self._persist_external(
                    job=job,
                    aisle=aisle,
                    asset=asset,
                    external=decision.external,
                    snapshot=snapshot,
                    reason=decision.reason,
                )
                result.applied += 1

            for conflict in plan.conflicts:
                if conflict.asset_id:
                    self._mark_conflict(job.id, conflict.asset_id, conflict.reason)
                    result.conflicts_marked += 1

            batch_row.status = GlobalFallbackBatchStatus.COMPLETED
            batch_row.updated_at = self._now()
            self._journal.save(batch_row)
            return result
        except Exception as exc:
            logger.exception(
                "global_fallback.merge_apply_failed job_id=%s batch=%s",
                job.id,
                batch_row.batch_fingerprint,
            )
            batch_row.status = GlobalFallbackBatchStatus.FAILED_RETRYABLE
            batch_row.error_code = "MERGE_APPLY_FAILED"
            batch_row.error_message = str(exc)[:500]
            batch_row.updated_at = self._now()
            self._journal.save(batch_row)
            result.failed = True
            result.error_code = "MERGE_APPLY_FAILED"
            result.error_message = str(exc)[:500]
            return result

    def _persist_external(
        self,
        *,
        job: Any,
        aisle: Any,
        asset: SourceAsset,
        external: Any,
        snapshot: Any,
        reason: str,
    ) -> None:
        result = ImageProcessingResult(
            job_id=job.id,
            asset_id=asset.id,
            status=ImageResultStatus.RESOLVED_EXTERNAL,
            processing_mode=EXTERNAL_PROVIDER_STRATEGY,
            resolved_by=EXTERNAL_PROVIDER_STRATEGY,
            internal_code=external.internal_code,
            quantity=external.quantity,
            normalized_result={
                "internal_code": external.internal_code,
                "quantity": external.quantity,
                "confidence": external.confidence,
                "source_image_id": external.source_image_id,
            },
            additional_fields={
                "fallback_mode": EXTERNAL_FALLBACK_MODE_GLOBAL_BATCH,
                "fallback_reason": reason,
                "execution_scope": ExecutionScope.AISLE_BATCH.value,
                "external_provider": getattr(snapshot, "provider", None),
                "external_model": getattr(snapshot, "model", None),
                "analysis_contract": GLOBAL_FALLBACK_ANALYSIS_CONTRACT,
                "schema_version": GLOBAL_FALLBACK_SCHEMA_VERSION,
            },
            evidence={
                "provider": getattr(snapshot, "provider", None),
                "model": getattr(snapshot, "model", None),
                "sanitized_entity": external.raw,
            },
            provider_name=getattr(snapshot, "provider", None),
            model_name=getattr(snapshot, "model", None),
            execution_scope=ExecutionScope.AISLE_BATCH,
            logical_asset_attempt=True,
        )
        self._persister.persist(
            result=result,
            inventory_id=aisle.inventory_id,
            aisle_id=aisle.id,
        )
        if self._state_repo is not None:
            state = self._state_repo.get_by_job_and_asset(job.id, asset.id)
            if state is not None:
                if reason == EXTERNAL_CODE_MISSING_QUANTITY_REASON:
                    state.status = JobAssetProcessingStatus.PENDING_MANUAL_REVIEW
                    state.error_code = "MISSING_QUANTITY"
                    state.error_message = reason
                else:
                    state.status = JobAssetProcessingStatus.RESOLVED
                    state.error_code = None
                    state.error_message = None
                state.last_strategy = EXTERNAL_PROVIDER_STRATEGY
                state.updated_at = self._now()
                self._state_repo.save(state)

    def _mark_conflict(self, job_id: str, asset_id: str, reason: str) -> None:
        if self._state_repo is None:
            return
        state = self._state_repo.get_by_job_and_asset(job_id, asset_id)
        if state is None:
            return
        if state.status == JobAssetProcessingStatus.RESOLVED:
            state.error_code = "GLOBAL_FALLBACK_CONFLICT"
            state.error_message = reason
        else:
            state.status = JobAssetProcessingStatus.PENDING_MANUAL_REVIEW
            state.error_code = "GLOBAL_FALLBACK_CONFLICT"
            state.error_message = reason
        state.updated_at = self._now()
        self._state_repo.save(state)

    def _now(self):
        if self._clock is not None:
            return self._clock.now()
        from datetime import datetime, timezone

        return datetime.now(timezone.utc)
