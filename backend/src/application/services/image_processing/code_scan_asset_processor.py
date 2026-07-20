"""Per-asset SINGLE_ASSET processing runner (CODE_SCAN / INTERNAL_OCR).

Neutral orchestration for one asset: reconcile → acquire → attempt → strategy.process →
persist → finalize. Strategy-specific naming belongs on the strategy, not this runner.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

from src.application.errors import AssetProcessingStateConcurrencyError
from src.application.ports.clock import Clock
from src.application.ports.image_processing_repositories import (
    JobAssetProcessingStateRepository,
    ProcessingAttemptRepository,
)
from src.application.services.image_processing.asset_processing_reconciler import (
    AssetProcessingReconciler,
)
from src.application.services.image_processing.external_provider_fallback_orchestrator import (
    ExternalFallbackOutcome,
    ExternalFallbackSnapshot,
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
from src.domain.image_processing.external_image_analysis_request import (
    ExternalImageAnalysisRequest,
)
from src.domain.image_processing.job_asset_processing_state import (
    JobAssetProcessingStatus,
)
from src.domain.image_processing.processing_attempt import (
    ProcessingAttempt,
    ProcessingAttemptStatus,
)
from src.domain.jobs.entities import Job

logger = logging.getLogger(__name__)

_DEFAULT_ATTEMPT_PROVIDER = "image_processing"


class SingleAssetProcessingStrategy(Protocol):
    strategy_key: str
    attempt_provider: str
    attempt_model: str

    def process(self, context: ImageProcessingContext) -> ImageProcessingResult: ...


class ExternalFallbackProcessor(Protocol):
    counters: object | None

    def process_if_eligible(
        self,
        *,
        job: Job,
        asset: SourceAsset,
        internal_result: ImageProcessingResult,
        worker_token: str,
        snapshot: ExternalFallbackSnapshot,
        client_id: str | None = None,
    ) -> ExternalFallbackOutcome: ...

    def finalize_after_persist(
        self,
        *,
        attempt: ProcessingAttempt,
        request: ExternalImageAnalysisRequest | None,
        result: ImageProcessingResult,
        position_id: str | None,
        active_result_id: str | None,
        persisted: bool,
    ) -> None: ...


@dataclass(frozen=True)
class SingleAssetProcessResult:
    processed: bool
    error: str | None = None


class SingleAssetStrategyProcessor:
    """Runs one physical image through any duck-typed per-image strategy."""

    def __init__(
        self,
        *,
        state_repo: JobAssetProcessingStateRepository,
        attempt_repo: ProcessingAttemptRepository,
        image_orchestrator: ImageProcessingOrchestrator,
        strategy: SingleAssetProcessingStrategy | None = None,
        code_scan_strategy: SingleAssetProcessingStrategy | None = None,
        result_persister: ProcessingResultPersister,
        clock: Clock,
        attempts_enabled: bool = True,
        reconciler: AssetProcessingReconciler | None = None,
        inventory_client_id: str | None = None,
        external_fallback: ExternalFallbackProcessor | None = None,
    ) -> None:
        self._state_repo = state_repo
        self._attempt_repo = attempt_repo
        self._image_orch = image_orchestrator
        self._strategy = strategy if strategy is not None else code_scan_strategy
        if self._strategy is None:
            raise ValueError("SingleAssetStrategyProcessor requires strategy= or code_scan_strategy=")
        self._result_persister = result_persister
        self._clock = clock
        self._attempts_enabled = attempts_enabled
        self._reconciler = reconciler
        self._inventory_client_id = inventory_client_id
        self._external_fallback = external_fallback

    def _attempt_provider(self) -> str:
        return str(
            getattr(self._strategy, "attempt_provider", None) or _DEFAULT_ATTEMPT_PROVIDER
        )

    def _attempt_model(self) -> str:
        return str(getattr(self._strategy, "attempt_model", None) or "unknown")

    def _resolve_client_id(self, job: Job) -> str | None:
        params = job.engine_params_json if isinstance(job.engine_params_json, dict) else {}
        snap_client = params.get("client_id")
        if isinstance(snap_client, str) and snap_client.strip():
            return snap_client.strip()
        if self._inventory_client_id and str(self._inventory_client_id).strip():
            return str(self._inventory_client_id).strip()
        return None

    def process_asset(
        self,
        *,
        job: Job,
        aisle: Aisle,
        asset: SourceAsset,
        strategy_key: str,
        worker_token: str,
    ) -> SingleAssetProcessResult:
        state = self._state_repo.get_by_job_and_asset(job.id, asset.id)
        if state is None or self._image_orch.is_terminal(state):
            return SingleAssetProcessResult(processed=False)

        if self._reconciler is not None:
            lookup = self._reconciler.find_active_result(
                job_id=job.id, asset_id=asset.id, aisle_id=aisle.id
            )
            if self._reconciler.reconcile_state_if_complete(
                state, lookup=lookup, strategy=strategy_key, aisle_id=aisle.id
            ):
                logger.info(
                    "image_processing.reconciled job_id=%s asset_id=%s strategy=%s",
                    job.id,
                    asset.id,
                    strategy_key,
                )
                return SingleAssetProcessResult(processed=True)

        acquired = self._image_orch.acquire_for_processing(
            job_id=job.id,
            asset_id=asset.id,
            strategy=strategy_key,
            worker_token=worker_token,
        )
        if acquired is None:
            return SingleAssetProcessResult(processed=False)

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
            client_id=self._resolve_client_id(job),
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
        logger.info(
            "image_processing.strategy_started job_id=%s asset_id=%s strategy=%s "
            "worker_token=%s provider=%s model=%s",
            job.id,
            asset.id,
            strategy_key,
            worker_token,
            context.provider_name,
            context.model_name,
        )
        try:
            result = self._strategy.process(context, asset)
        except Exception as exc:
            logger.exception(
                "image_processing.strategy_failed job_id=%s asset_id=%s strategy=%s",
                job.id,
                asset.id,
                strategy_key,
            )
            error = f"strategy_exception:{asset.id}"
            result = self._failed_technical(
                job,
                asset,
                strategy_key,
                f"{strategy_key}_STRATEGY_EXCEPTION",
                str(exc),
            )

        if result.status is ImageResultStatus.RESOLVED_INTERNAL:
            result, persist_error = self._apply_persist(
                job=job, aisle=aisle, asset=asset, strategy_key=strategy_key, result=result
            )
            error = error or persist_error
            if (
                result.status is ImageResultStatus.RESOLVED_INTERNAL
                and self._external_fallback is not None
                and self._external_fallback.counters is not None
            ):
                self._external_fallback.counters.resolved_internal += 1

        logger.info(
            "image_processing.strategy_completed job_id=%s asset_id=%s strategy=%s "
            "status=%s error_code=%s duration_ms=%s",
            job.id,
            asset.id,
            strategy_key,
            result.status.value,
            result.error_code,
            result.processing_duration_ms,
        )

        finalize_strategy = strategy_key
        finalize_attempt = attempt

        # Phase 5: close the internal attempt, then optionally run EXTERNAL_PROVIDER.
        if (
            result.status is not ImageResultStatus.RESOLVED_INTERNAL
            and self._external_fallback is not None
        ):
            if attempt is not None and self._attempts_enabled:
                self._image_orch.complete_attempt_from_result(
                    attempt=attempt,
                    result=result,
                    duration_ms=result.processing_duration_ms,
                )
                finalize_attempt = None

            params = job.engine_params_json if isinstance(job.engine_params_json, dict) else {}
            ident = params.get("identification_execution")
            snapshot = ExternalFallbackSnapshot.from_identification_execution(
                ident if isinstance(ident, dict) else None
            )
            client_id = self._resolve_client_id(job)
            if snapshot is not None and snapshot.enabled:
                outcome = self._external_fallback.process_if_eligible(
                    job=job,
                    asset=asset,
                    internal_result=result,
                    worker_token=worker_token,
                    snapshot=snapshot,
                    client_id=client_id,
                )
                if outcome.cancelled:
                    # Do not finalize as FAILED_TECHNICAL; leave state for cancel coordinator.
                    if acquired is not None:
                        try:
                            self._image_orch.mark_cancelled(acquired, outcome.attempt)
                        except Exception:
                            logger.warning(
                                "image_processing.cancel_finalize_failed job_id=%s asset_id=%s",
                                job.id,
                                asset.id,
                            )
                    return SingleAssetProcessResult(processed=True, error=None)
                if not outcome.skipped and outcome.result is not None:
                    result = outcome.result
                    finalize_strategy = "EXTERNAL_PROVIDER"
                    finalize_attempt = outcome.attempt
                    if result.status is ImageResultStatus.RESOLVED_EXTERNAL:
                        result, persist_error = self._apply_persist(
                            job=job,
                            aisle=aisle,
                            asset=asset,
                            strategy_key=finalize_strategy,
                            result=result,
                        )
                        error = error or persist_error
                        position_id = (result.additional_fields or {}).get("position_id")
                        active_id = (result.additional_fields or {}).get("active_result_id")
                        persisted_ok = result.status is ImageResultStatus.RESOLVED_EXTERNAL
                        if outcome.attempt is not None:
                            self._external_fallback.finalize_after_persist(
                                attempt=outcome.attempt,
                                request=outcome.request,
                                result=result,
                                position_id=str(position_id) if position_id else None,
                                active_result_id=str(active_id) if active_id else None,
                                persisted=persisted_ok,
                            )
                        # Attempt already finalized by finalize_after_persist.
                        finalize_attempt = None
                    elif outcome.attempt is not None:
                        # Terminal non-resolved already closed inside orchestrator.
                        finalize_attempt = None

        self._finalize(
            job=job,
            asset=asset,
            acquired=acquired,
            attempt=finalize_attempt,
            result=result,
            strategy_key=finalize_strategy,
        )
        return SingleAssetProcessResult(processed=True, error=error)

    def _apply_persist(
        self,
        *,
        job: Job,
        aisle: Aisle,
        asset: SourceAsset,
        strategy_key: str,
        result: ImageProcessingResult,
    ) -> tuple[ImageProcessingResult, str | None]:
        logger.info(
            "image_processing.persistence_started job_id=%s asset_id=%s strategy=%s",
            job.id,
            asset.id,
            strategy_key,
        )
        try:
            outcome = self._result_persister.persist(
                result=result,
                inventory_id=aisle.inventory_id,
                aisle_id=aisle.id,
            )
        except Exception as exc:
            logger.exception(
                "image_processing.persistence_failed job_id=%s asset_id=%s strategy=%s",
                job.id,
                asset.id,
                strategy_key,
            )
            return (
                self._failed_technical(
                    job,
                    asset,
                    strategy_key,
                    "PROCESSING_PERSISTENCE_FAILED",
                    str(exc),
                ),
                f"persist_failed:{asset.id}",
            )

        if outcome.persisted or outcome.reconciled:
            active_id = outcome.active_result_id or outcome.position_id
            result.additional_fields["active_result_id"] = active_id
            result.additional_fields["position_id"] = outcome.position_id
            result.additional_fields["persistence_status"] = (
                "persisted" if outcome.persisted else "reconciled"
            )
            logger.info(
                "image_processing.persistence_completed job_id=%s asset_id=%s strategy=%s "
                "persistence_outcome=%s position_id=%s",
                job.id,
                asset.id,
                strategy_key,
                "persisted" if outcome.persisted else "reconciled",
                outcome.position_id,
            )
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
                    job, asset, strategy_key, "PROCESSING_INCOMPLETE_RESULT", result
                ),
                None,
            )
        return (
            self._failed_technical(
                job,
                asset,
                strategy_key,
                "PROCESSING_PERSISTENCE_FAILED",
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
                "image_processing.state_conflict job_id=%s asset_id=%s strategy=%s",
                job.id,
                asset.id,
                strategy_key,
            )

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
            return
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
            logger.warning(
                "image_processing.close_attempt_failed attempt_id=%s",
                getattr(attempt, "id", None),
            )

    def _failed_technical(
        self,
        job: Job,
        asset: SourceAsset,
        strategy_key: str,
        error_code: str,
        message: str,
    ) -> ImageProcessingResult:
        return ImageProcessingResult(
            job_id=job.id,
            asset_id=asset.id,
            status=ImageResultStatus.FAILED_TECHNICAL,
            processing_mode=strategy_key,
            resolved_by=strategy_key,
            error_code=error_code,
            error_message=(message or "")[:500],
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
            processing_mode=strategy_key,
            resolved_by=strategy_key,
            internal_code=prior.internal_code,
            quantity=prior.quantity,
            additional_fields=dict(prior.additional_fields),
            warnings=list(prior.warnings) + [error_code],
            validation_errors=list(prior.validation_errors) + [error_code],
            evidence=prior.evidence,
            error_code=error_code,
            execution_scope=ExecutionScope.SINGLE_ASSET,
            logical_asset_attempt=False,
        )


# Temporary aliases (Phase 3/4 compatibility)
CodeScanAssetResult = SingleAssetProcessResult
CodeScanAssetProcessor = SingleAssetStrategyProcessor


__all__ = [
    "CodeScanAssetProcessor",
    "CodeScanAssetResult",
    "SingleAssetProcessResult",
    "SingleAssetStrategyProcessor",
]
