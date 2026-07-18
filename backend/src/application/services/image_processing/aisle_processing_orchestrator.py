"""Aisle-level orchestrator — ensure states, run legacy batch, synthesize per-asset (Phase 2)."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from src.application.ports.clock import Clock
from src.application.ports.image_processing_repositories import (
    AssetProgressCounts,
    JobAssetProcessingStateRepository,
    ProcessingAttemptRepository,
)
from src.application.services.image_processing.image_processing_orchestrator import (
    ImageProcessingOrchestrator,
)
from src.application.services.image_processing.legacy_llm_processing_strategy import (
    LegacyBatchOutcome,
    LegacyLlmProcessingStrategy,
)
from src.application.services.image_processing.processing_strategy_resolver import (
    ProcessingStrategyResolver,
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
    JobAssetProcessingState,
    JobAssetProcessingStatus,
)
from src.domain.jobs.entities import Job

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AisleOrchestratorOutcome:
    legacy: LegacyBatchOutcome
    progress: AssetProgressCounts
    strategy_key: str


class AisleProcessingOrchestrator:
    """Coordinates per-asset bookkeeping around the existing AISLE_BATCH legacy run."""

    def __init__(
        self,
        state_repo: JobAssetProcessingStateRepository,
        attempt_repo: ProcessingAttemptRepository,
        clock: Clock,
        image_orchestrator: ImageProcessingOrchestrator,
        strategy_resolver: ProcessingStrategyResolver,
        legacy_strategy: LegacyLlmProcessingStrategy,
        *,
        attempts_enabled: bool = True,
        abandoned_processing_ttl_seconds: int = 900,
    ) -> None:
        self._state_repo = state_repo
        self._attempt_repo = attempt_repo
        self._clock = clock
        self._image_orch = image_orchestrator
        self._resolver = strategy_resolver
        self._legacy = legacy_strategy
        self._attempts_enabled = attempts_enabled
        self._abandoned_ttl = abandoned_processing_ttl_seconds

    def ensure_asset_states(
        self, job: Job, assets: Sequence[SourceAsset]
    ) -> list[JobAssetProcessingState]:
        now = self._clock.now()
        out: list[JobAssetProcessingState] = []
        for asset in assets:
            existing = self._state_repo.get_by_job_and_asset(job.id, asset.id)
            if existing is not None:
                out.append(existing)
                continue
            state = JobAssetProcessingState(
                id=str(uuid.uuid4()),
                job_id=job.id,
                asset_id=asset.id,
                status=JobAssetProcessingStatus.PENDING,
                created_at=now,
                updated_at=now,
                execution_scope=ExecutionScope.AISLE_BATCH.value,
            )
            self._state_repo.save(state)
            out.append(state)
        logger.info(
            "aisle_orchestrator.states_ensured job_id=%s total=%s",
            job.id,
            len(out),
        )
        return out

    def recover_abandoned_processing(self, job_id: str) -> int:
        cutoff = self._clock.now() - timedelta(seconds=self._abandoned_ttl)
        recovered = 0
        for state in self._state_repo.list_by_job(job_id):
            if state.status != JobAssetProcessingStatus.PROCESSING:
                continue
            ref = state.updated_at or state.started_at
            if ref is None or ref > cutoff:
                continue
            age_s = int((self._clock.now() - ref).total_seconds())
            state.status = JobAssetProcessingStatus.PENDING
            state.error_code = "ABANDONED_PROCESSING_RECOVERED"
            state.error_message = f"Recovered after {age_s}s without progress"
            state.updated_at = self._clock.now()
            state.version = int(state.version or 1) + 1
            self._state_repo.save(state)
            recovered += 1
            logger.warning(
                "aisle_orchestrator.recovered_abandoned job_id=%s asset_id=%s "
                "age_seconds=%s reason=%s",
                job_id,
                state.asset_id,
                age_s,
                state.error_code,
            )
        return recovered

    def process_with_legacy_batch(
        self,
        *,
        job: Job,
        aisle: Aisle,
        assets: Sequence[SourceAsset],
        runner_kwargs: dict[str, Any],
        pipeline_enabled: bool,
        orchestrator_enabled: bool,
        cancel_requested: bool = False,
    ) -> AisleOrchestratorOutcome:
        strategy_key = self._resolver.resolve_strategy_key(
            job,
            pipeline_enabled=pipeline_enabled,
            orchestrator_enabled=orchestrator_enabled,
        )
        self.ensure_asset_states(job, assets)
        self.recover_abandoned_processing(job.id)

        if cancel_requested:
            self._cancel_pending(job.id)
            progress = self._state_repo.aggregate_progress(job.id)
            return AisleOrchestratorOutcome(
                legacy=LegacyBatchOutcome(ok=False, cancelled=True),
                progress=progress,
                strategy_key=strategy_key,
            )

        # Mark all non-terminal as PROCESSING for the batch scope (concurrency default 1).
        for asset in assets:
            state = self._state_repo.get_by_job_and_asset(job.id, asset.id)
            if state is None or self._image_orch.is_terminal(state):
                continue
            acquired = self._image_orch.acquire_for_processing(
                job_id=job.id, asset_id=asset.id, strategy=strategy_key
            )
            if acquired is None and state.status == JobAssetProcessingStatus.PENDING:
                logger.info(
                    "aisle_orchestrator.skip_busy job_id=%s asset_id=%s",
                    job.id,
                    asset.id,
                )

        outcome = self._legacy.process_aisle_batch(
            job=job, assets=assets, runner_kwargs=runner_kwargs
        )
        self._synthesize_after_batch(
            job=job,
            aisle=aisle,
            assets=assets,
            outcome=outcome,
            strategy_key=strategy_key,
        )
        progress = self._state_repo.aggregate_progress(job.id)
        logger.info(
            "aisle_orchestrator.batch_complete job_id=%s strategy=%s "
            "progress_total=%s resolved=%s unrecognized=%s failed=%s",
            job.id,
            strategy_key,
            progress.total,
            progress.resolved,
            progress.unrecognized,
            progress.failed,
        )
        return AisleOrchestratorOutcome(
            legacy=outcome, progress=progress, strategy_key=strategy_key
        )

    def _synthesize_after_batch(
        self,
        *,
        job: Job,
        aisle: Aisle,
        assets: Sequence[SourceAsset],
        outcome: LegacyBatchOutcome,
        strategy_key: str,
    ) -> None:
        for asset in assets:
            state = self._state_repo.get_by_job_and_asset(job.id, asset.id)
            if state is None:
                continue
            # Do not reprocess assets that already finished successfully on a prior recovery.
            if self._image_orch.is_terminal(state):
                continue

            context = ImageProcessingContext(
                job_id=job.id,
                asset_id=asset.id,
                aisle_id=aisle.id,
                inventory_id=aisle.inventory_id,
                client_id=None,
                identification_mode=job.identification_mode,
                execution_strategy=job.execution_strategy,
                configuration_snapshot_version=job.configuration_snapshot_version,
                provider_name=job.provider_name,
                model_name=job.model_name,
                prompt_key=job.prompt_key,
                prompt_version=job.prompt_version,
                attempt_number=max(1, int(state.attempt_count or 0) + 1),
                execution_scope=ExecutionScope.AISLE_BATCH,
                asset_reference=asset.original_filename,
            )
            attempt = self._image_orch.start_attempt(context, strategy=strategy_key)

            if outcome.cancelled:
                result = ImageProcessingResult(
                    job_id=job.id,
                    asset_id=asset.id,
                    status=ImageResultStatus.FAILED_TECHNICAL,
                    processing_mode=job.identification_mode.value,
                    resolved_by=strategy_key,
                    error_code="CANCELLED",
                    error_message="Job cancelled during aisle batch",
                    execution_scope=ExecutionScope.AISLE_BATCH,
                    provider_name=job.provider_name,
                    model_name=job.model_name,
                )
                self._image_orch.mark_cancelled(state, attempt)
                continue

            if not outcome.ok:
                result = ImageProcessingResult(
                    job_id=job.id,
                    asset_id=asset.id,
                    status=ImageResultStatus.FAILED_TECHNICAL,
                    processing_mode=job.identification_mode.value,
                    resolved_by=strategy_key,
                    error_code="LEGACY_BATCH_FAILED",
                    error_message=outcome.error_message or "Legacy aisle batch failed",
                    execution_scope=ExecutionScope.AISLE_BATCH,
                    provider_name=job.provider_name,
                    model_name=job.model_name,
                )
            elif asset.id in outcome.assets_with_result:
                result = ImageProcessingResult(
                    job_id=job.id,
                    asset_id=asset.id,
                    status=ImageResultStatus.RESOLVED_EXTERNAL,
                    processing_mode=job.identification_mode.value,
                    resolved_by=strategy_key,
                    execution_scope=ExecutionScope.AISLE_BATCH,
                    provider_name=job.provider_name,
                    model_name=job.model_name,
                    warnings=[
                        "Logical asset result synthesized from AISLE_BATCH legacy coverage; "
                        "provider did not process this asset as an isolated request."
                    ],
                )
            else:
                result = ImageProcessingResult(
                    job_id=job.id,
                    asset_id=asset.id,
                    status=ImageResultStatus.UNRECOGNIZED,
                    processing_mode=job.identification_mode.value,
                    resolved_by=strategy_key,
                    execution_scope=ExecutionScope.AISLE_BATCH,
                    provider_name=job.provider_name,
                    model_name=job.model_name,
                    warnings=[
                        "No position/evidence linked for asset after AISLE_BATCH legacy run."
                    ],
                )

            # Reload state after acquire
            state = self._state_repo.get_by_job_and_asset(job.id, asset.id) or state
            self._image_orch.finalize_from_result(
                state=state,
                attempt=attempt,
                result=result,
                strategy=strategy_key,
            )

    def _cancel_pending(self, job_id: str) -> None:
        for state in self._state_repo.list_by_job(job_id):
            if state.status in (
                JobAssetProcessingStatus.PENDING,
                JobAssetProcessingStatus.PROCESSING,
            ):
                self._image_orch.mark_cancelled(state, None)
