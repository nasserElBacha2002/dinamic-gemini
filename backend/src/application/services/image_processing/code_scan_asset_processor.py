"""Phase 3 corrections — per-asset CODE_SCAN processing (extracted from the orchestrator).

Owns everything that happens to ONE asset during a CODE_SCAN run: reconcile against an
already-persisted result, acquire the state, open a code-scan attempt, run the deterministic
scan strategy, honor the persist outcome (never finalize RESOLVED unless a position actually
exists), and finalize the per-asset state with concurrency-conflict recovery.

Extracted so :class:`AisleProcessingOrchestrator` stays a coordinator rather than growing an
ever-larger god method. The orchestrator still owns the run loop, progress publishing, and
cancellation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from src.application.errors import AssetProcessingStateConcurrencyError
from src.application.ports.clock import Clock
from src.application.ports.image_processing_repositories import (
    JobAssetProcessingStateRepository,
    ProcessingAttemptRepository,
)
from src.application.services.image_processing.asset_processing_reconciler import (
    AssetProcessingReconciler,
)
from src.application.services.image_processing.image_processing_orchestrator import (
    ImageProcessingOrchestrator,
)
from src.application.services.image_processing.processing_result_persister import (
    PersistSkipReason,
    ProcessingResultPersister,
)
from src.domain.aisle.entities import Aisle
from src.domain.assets.entities import SourceAsset
from src.domain.image_processing.contracts import (
    ExecutionScope,
    ImageProcessingContext,
    ImageProcessingResult,
    ImageResultStatus,
)
from src.domain.image_processing.job_asset_processing_state import (
    JobAssetProcessingStatus,
)
from src.domain.image_processing.processing_attempt import ProcessingAttemptStatus
from src.domain.jobs.entities import Job

logger = logging.getLogger(__name__)

_CODE_SCAN_ATTEMPT_PROVIDER = "code_scan"


@dataclass(frozen=True)
class CodeScanAssetResult:
    processed: bool
    error: str | None = None


class CodeScanAssetProcessor:
    def __init__(
        self,
        *,
        state_repo: JobAssetProcessingStateRepository,
        attempt_repo: ProcessingAttemptRepository,
        image_orchestrator: ImageProcessingOrchestrator,
        code_scan_strategy: object,
        result_persister: ProcessingResultPersister,
        clock: Clock,
        attempts_enabled: bool = True,
        reconciler: AssetProcessingReconciler | None = None,
    ) -> None:
        self._state_repo = state_repo
        self._attempt_repo = attempt_repo
        self._image_orch = image_orchestrator
        self._code_scan_strategy = code_scan_strategy
        self._result_persister = result_persister
        self._clock = clock
        self._attempts_enabled = attempts_enabled
        self._reconciler = reconciler

    # ------------------------------------------------------------------

    def _attempt_provider(self) -> str:
        return str(
            getattr(self._code_scan_strategy, "attempt_provider", _CODE_SCAN_ATTEMPT_PROVIDER)
            or _CODE_SCAN_ATTEMPT_PROVIDER
        )

    def _attempt_model(self) -> str:
        return str(getattr(self._code_scan_strategy, "attempt_model", "pyzbar") or "pyzbar")

    def process_asset(
        self,
        *,
        job: Job,
        aisle: Aisle,
        asset: SourceAsset,
        strategy_key: str,
        worker_token: str,
    ) -> CodeScanAssetResult:
        state = self._state_repo.get_by_job_and_asset(job.id, asset.id)
        if state is None or self._image_orch.is_terminal(state):
            return CodeScanAssetResult(processed=False)

        # Reconcile before scanning: a prior worker may have persisted a complete result but
        # crashed before finalizing this state. Never rescan (or downgrade) a covered asset.
        if self._reconciler is not None:
            lookup = self._reconciler.find_active_result(
                job_id=job.id, asset_id=asset.id, aisle_id=aisle.id
            )
            if self._reconciler.reconcile_state_if_complete(
                state, lookup=lookup, strategy=strategy_key, aisle_id=aisle.id
            ):
                logger.info(
                    "code_scan.reconciled_before_scan job_id=%s asset_id=%s",
                    job.id,
                    asset.id,
                )
                return CodeScanAssetResult(processed=True)

        acquired = self._image_orch.acquire_for_processing(
            job_id=job.id,
            asset_id=asset.id,
            strategy=strategy_key,
            worker_token=worker_token,
        )
        if acquired is None:
            return CodeScanAssetResult(processed=False)

        attempt = None
        attempt_number = int(acquired.attempt_count or 0) + 1
        if self._attempts_enabled:
            attempt = self._attempt_repo.create_next_attempt(
                job_id=job.id,
                asset_id=asset.id,
                strategy=strategy_key,
                status=ProcessingAttemptStatus.STARTED,
                now=self._clock.now(),
                provider=self._attempt_provider(),
                model=self._attempt_model(),
                execution_scope=ExecutionScope.SINGLE_ASSET.value,
                configuration_snapshot_version=job.configuration_snapshot_version,
                parent_batch_attempt_id=None,
                batch_execution_id=None,
                worker_token=worker_token,
                logical_asset_attempt=False,
            )
            attempt_number = attempt.attempt_number

        context = ImageProcessingContext(
            job_id=job.id,
            asset_id=asset.id,
            aisle_id=aisle.id,
            inventory_id=aisle.inventory_id,
            client_id=None,
            identification_mode=job.identification_mode,
            execution_strategy=job.execution_strategy,
            configuration_snapshot_version=job.configuration_snapshot_version,
            provider_name=self._attempt_provider(),
            model_name=self._attempt_model(),
            prompt_key=job.prompt_key,
            prompt_version=job.prompt_version,
            attempt_number=attempt_number,
            execution_scope=ExecutionScope.SINGLE_ASSET,
            asset_reference=asset.storage_key,
        )

        error: str | None = None
        try:
            result = self._code_scan_strategy.process(context, asset)
        except Exception as exc:  # defensive: strategy must not crash the run
            logger.exception(
                "code_scan.strategy_exception job_id=%s asset_id=%s", job.id, asset.id
            )
            error = f"strategy_exception:{asset.id}"
            result = self._failed_technical(
                job, asset, strategy_key, "CODE_SCAN_STRATEGY_EXCEPTION", str(exc)
            )

        if result.status is ImageResultStatus.RESOLVED_INTERNAL:
            result, persist_error = self._apply_persist(
                job=job, aisle=aisle, asset=asset, strategy_key=strategy_key, result=result
            )
            error = error or persist_error

        self._finalize(
            job=job,
            asset=asset,
            acquired=acquired,
            attempt=attempt,
            result=result,
            strategy_key=strategy_key,
        )
        return CodeScanAssetResult(processed=True, error=error)

    # ------------------------------------------------------------------

    def _apply_persist(
        self,
        *,
        job: Job,
        aisle: Aisle,
        asset: SourceAsset,
        strategy_key: str,
        result: ImageProcessingResult,
    ) -> tuple[ImageProcessingResult, str | None]:
        try:
            outcome = self._result_persister.persist(
                result=result,
                inventory_id=aisle.inventory_id,
                aisle_id=aisle.id,
            )
        except Exception as exc:
            logger.exception(
                "code_scan.persist_failed job_id=%s asset_id=%s", job.id, asset.id
            )
            return (
                self._failed_technical(
                    job, asset, strategy_key, "CODE_SCAN_PERSISTENCE_FAILED", str(exc)
                ),
                f"persist_failed:{asset.id}",
            )

        if outcome.persisted or outcome.reconciled:
            active_id = outcome.active_result_id or outcome.position_id
            result.additional_fields["active_result_id"] = active_id
            result.additional_fields["position_id"] = outcome.position_id
            return result, None

        reason = outcome.skipped_reason
        if reason is PersistSkipReason.MANUAL_RESULT_EXISTS:
            return (
                self._pending_manual_review(
                    job, asset, strategy_key, "MANUAL_RESULT_EXISTS", result
                ),
                None,
            )
        if reason is PersistSkipReason.ASSET_NOT_IN_SNAPSHOT:
            return (
                self._failed_technical(
                    job,
                    asset,
                    strategy_key,
                    "ASSET_NOT_IN_JOB_SNAPSHOT",
                    "Asset is not part of the job source-asset snapshot.",
                ),
                f"asset_not_in_snapshot:{asset.id}",
            )
        if reason in (
            PersistSkipReason.MISSING_CODE_OR_QUANTITY,
            PersistSkipReason.NON_POSITIVE_QUANTITY,
        ):
            return (
                self._pending_manual_review(
                    job, asset, strategy_key, "CODE_SCAN_INCOMPLETE_RESULT", result
                ),
                None,
            )
        # CONCURRENCY_CONFLICT (unreconciled), PERSISTENCE_ERROR, NOT_RESOLVED_INTERNAL, or None.
        return (
            self._failed_technical(
                job,
                asset,
                strategy_key,
                "CODE_SCAN_PERSISTENCE_FAILED",
                f"persist skipped without a position: {reason.value if reason else 'unknown'}",
            ),
            f"persist_not_resolved:{asset.id}",
        )

    def _finalize(
        self,
        *,
        job: Job,
        asset: SourceAsset,
        acquired,
        attempt,
        result: ImageProcessingResult,
        strategy_key: str,
    ) -> None:
        try:
            self._image_orch.finalize_from_result(
                state=acquired, attempt=attempt, result=result, strategy=strategy_key
            )
            return
        except AssetProcessingStateConcurrencyError:
            logger.warning(
                "code_scan.state_conflict job_id=%s asset_id=%s", job.id, asset.id
            )

        # F — reconcile after a conflict: another worker finalized this asset first.
        reloaded = self._state_repo.get_by_job_and_asset(job.id, asset.id)
        if reloaded is not None and reloaded.status is JobAssetProcessingStatus.RESOLVED:
            self._close_attempt_reconciled(attempt)
            return
        if (
            reloaded is not None
            and reloaded.status is JobAssetProcessingStatus.PROCESSING
            and self._reconciler is not None
        ):
            self._reconciler.reconcile_state_if_complete(reloaded, strategy=strategy_key)
        self._close_attempt_reconciled(attempt)

    def _close_attempt_reconciled(self, attempt) -> None:
        if attempt is None or not self._attempts_enabled:
            return
        try:
            attempt.status = ProcessingAttemptStatus.CANCELLED
            attempt.finished_at = self._clock.now()
            attempt.error_code = "RECONCILED_BY_OTHER_WORKER"
            attempt.error_message = "Asset finalized by a concurrent worker before this attempt."
            self._attempt_repo.save(attempt)
        except Exception:
            logger.warning("code_scan.close_attempt_failed attempt_id=%s", getattr(attempt, "id", None))

    # ------------------------------------------------------------------

    def _failed_technical(
        self,
        job: Job,
        asset: SourceAsset,
        strategy_key: str,
        error_code: str,
        error_message: str,
    ) -> ImageProcessingResult:
        return ImageProcessingResult(
            job_id=job.id,
            asset_id=asset.id,
            status=ImageResultStatus.FAILED_TECHNICAL,
            processing_mode=job.identification_mode.value,
            resolved_by=strategy_key,
            error_code=error_code,
            error_message=error_message,
            execution_scope=ExecutionScope.SINGLE_ASSET,
            logical_asset_attempt=False,
        )

    def _pending_manual_review(
        self,
        job: Job,
        asset: SourceAsset,
        strategy_key: str,
        error_code: str,
        prior: ImageProcessingResult,
    ) -> ImageProcessingResult:
        return ImageProcessingResult(
            job_id=job.id,
            asset_id=asset.id,
            status=ImageResultStatus.PENDING_MANUAL_REVIEW,
            processing_mode=job.identification_mode.value,
            resolved_by=strategy_key,
            internal_code=prior.internal_code,
            evidence=prior.evidence,
            warnings=list(prior.warnings),
            error_code=error_code,
            execution_scope=ExecutionScope.SINGLE_ASSET,
            logical_asset_attempt=False,
        )


__all__ = ["CodeScanAssetProcessor", "CodeScanAssetResult"]
