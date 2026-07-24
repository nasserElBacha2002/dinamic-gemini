"""Aisle-level orchestrator — lease, batch attempt, per-asset bookkeeping (Phase 2 corrections).

Coordinates one physical AISLE_BATCH legacy run behind an exclusive
:class:`JobProcessingLease` (so two concurrent workers never re-run the same batch for the
same job), tracks a :class:`BatchProcessingAttempt` for that physical run, and synthesizes
logical per-asset results afterward via :class:`AssetResultCoverageResolver` (never from the
runner's own bookkeeping — the runner is a legacy black box we do not trust for per-asset
attribution).
"""

from __future__ import annotations

import logging
import threading
import uuid
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from src.application.errors import (
    AssetProcessingStateConcurrencyError,
    CodeScanPipelineMisconfiguredError,
)
from src.application.ports.clock import Clock
from src.application.ports.image_processing_repositories import (
    AssetProgressCounts,
    BatchProcessingAttemptRepository,
    JobAssetProcessingStateRepository,
    JobProcessingLeaseRepository,
    ProcessingAttemptRepository,
)
from src.application.services.image_processing.asset_result_coverage_resolver import (
    AssetResultCoverageResolver,
    AssetResultCoverageStatus,
)
from src.application.services.image_processing.code_scan_asset_processor import (
    CodeScanAssetProcessor,
)
from src.application.services.image_processing.code_scan_job_outcome_policy import (
    CodeScanJobOutcome,
)
from src.application.services.image_processing.code_scan_job_outcome_policy import (
    decide as decide_code_scan_job_outcome,
)
from src.application.services.image_processing.image_processing_orchestrator import (
    ImageProcessingOrchestrator,
)
from src.application.services.image_processing.legacy_llm_processing_strategy import (
    LegacyBatchOutcome,
    LegacyBatchRunner,
    LegacyLlmProcessingStrategy,
)
from src.application.services.image_processing.processing_strategy_resolver import (
    ProcessingStrategyResolver,
)
from src.domain.aisle.entities import Aisle
from src.domain.assets.entities import SourceAsset
from src.domain.image_processing.batch_processing_attempt import (
    BatchProcessingAttempt,
    BatchProcessingAttemptStatus,
)
from src.domain.image_processing.contracts import (
    ExecutionScope,
    ImageProcessingResult,
    ImageResultStatus,
)
from src.domain.image_processing.job_asset_processing_state import (
    JobAssetProcessingState,
    JobAssetProcessingStatus,
)
from src.domain.image_processing.processing_attempt import (
    ProcessingAttempt,
    ProcessingAttemptStatus,
)
from src.domain.jobs.entities import Job
from src.pipeline.errors import PipelineCancellationRequestedError

if TYPE_CHECKING:
    from src.application.services.image_processing.apply_authoritative_local_results import (
        ApplyAuthoritativeLocalResultsService,
    )
    from src.application.services.image_processing.asset_processing_reconciler import (
        AssetProcessingReconciler,
    )
    from src.application.services.image_processing.code_scan_processing_strategy import (
        CodeScanProcessingStrategy,
    )
    from src.application.services.image_processing.processing_result_persister import (
        ProcessingResultPersister,
    )

logger = logging.getLogger(__name__)

# K — module-level counter for progress-publish failures (no external metrics dependency).
asset_progress_publish_failed_total = 0

_COVERAGE_TO_RESULT_STATUS = {
    AssetResultCoverageStatus.RESOLVED: ImageResultStatus.RESOLVED_EXTERNAL,
    AssetResultCoverageStatus.UNRECOGNIZED: ImageResultStatus.UNRECOGNIZED,
    AssetResultCoverageStatus.PENDING_RECONCILIATION: ImageResultStatus.PENDING_MANUAL_REVIEW,
}


@dataclass(frozen=True)
class AisleOrchestratorOutcome:
    legacy: LegacyBatchOutcome
    progress: AssetProgressCounts
    strategy_key: str


@dataclass(frozen=True)
class CodeScanAisleOutcome:
    """Outcome of a Phase 3 CODE_SCAN per-asset run (no legacy LLM batch)."""

    ok: bool
    cancelled: bool
    progress: AssetProgressCounts
    strategy_key: str
    job_outcome: CodeScanJobOutcome = CodeScanJobOutcome.SUCCEEDED
    error_message: str | None = None
    assets_eligible: int = 0
    assets_started: int = 0


class AisleProcessingOrchestrator:
    """Coordinates per-asset bookkeeping + exclusive lease around one AISLE_BATCH legacy run."""

    def __init__(
        self,
        state_repo: JobAssetProcessingStateRepository,
        attempt_repo: ProcessingAttemptRepository,
        lease_repo: JobProcessingLeaseRepository,
        batch_attempt_repo: BatchProcessingAttemptRepository,
        clock: Clock,
        image_orchestrator: ImageProcessingOrchestrator,
        strategy_resolver: ProcessingStrategyResolver,
        legacy_strategy: LegacyLlmProcessingStrategy,
        coverage_resolver: AssetResultCoverageResolver,
        *,
        attempts_enabled: bool = True,
        abandoned_processing_ttl_seconds: int = 900,
        lease_duration_seconds: int = 900,
        lease_recovery_sweep_limit: int = 100,
        code_scan_strategy: CodeScanProcessingStrategy | None = None,
        result_persister: ProcessingResultPersister | None = None,
        code_scan_concurrency: int = 1,
        reconciler: AssetProcessingReconciler | None = None,
        external_fallback=None,
        apply_authoritative_local: ApplyAuthoritativeLocalResultsService | None = None,
    ) -> None:
        self._state_repo = state_repo
        self._attempt_repo = attempt_repo
        self._lease_repo = lease_repo
        self._batch_attempt_repo = batch_attempt_repo
        self._clock = clock
        self._image_orch = image_orchestrator
        self._resolver = strategy_resolver
        self._legacy = legacy_strategy
        self._coverage = coverage_resolver
        self._attempts_enabled = attempts_enabled
        self._abandoned_ttl = abandoned_processing_ttl_seconds
        self._lease_duration_seconds = lease_duration_seconds
        self._lease_recovery_sweep_limit = lease_recovery_sweep_limit
        self._code_scan_strategy = code_scan_strategy
        self._result_persister = result_persister
        self._code_scan_concurrency = max(1, int(code_scan_concurrency or 1))
        self._reconciler = reconciler
        self._external_fallback = external_fallback
        self._apply_authoritative_local = apply_authoritative_local

    # ------------------------------------------------------------------
    # State bootstrap
    # ------------------------------------------------------------------

    def ensure_asset_states(
        self,
        job: Job,
        assets: Sequence[SourceAsset],
        *,
        execution_scope: ExecutionScope = ExecutionScope.AISLE_BATCH,
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
                execution_scope=execution_scope.value,
            )
            self._state_repo.save(state)
            out.append(state)
        logger.info(
            "aisle_orchestrator.states_ensured job_id=%s total=%s",
            job.id,
            len(out),
        )
        return out

    # ------------------------------------------------------------------
    # Recovery (lease + states + attempts, jointly)
    # ------------------------------------------------------------------

    def recover_abandoned_processing(self, job_id: str) -> list[str]:
        """Reset stale ``PROCESSING`` states for ``job_id`` back to ``PENDING``.

        Returns the recovered ``asset_id`` list so callers can close their orphaned
        logical attempts too. Uses ``save_with_ownership`` so a concurrent recovery sweep
        (or a worker that was not actually abandoned) loses the race harmlessly.
        Uses the dedicated abandoned query (not a full job scan + in-memory filter).
        """
        now = self._clock.now()
        cutoff = now - timedelta(seconds=self._abandoned_ttl)
        recovered: list[str] = []
        for state in self._state_repo.list_abandoned_processing(
            older_than=cutoff,
            limit=self._lease_recovery_sweep_limit,
            job_id=job_id,
            as_of=now,
        ):
            age_s = int((now - (state.updated_at or state.started_at or now)).total_seconds())
            # E — if a complete result already exists (position persisted, state never
            # finalized), reconcile straight to RESOLVED instead of resetting to PENDING for
            # a wasteful (and potentially downgrading) rescan.
            if self._reconciler is not None and self._reconciler.reconcile_state_if_complete(state):
                recovered.append(state.asset_id)
                logger.info(
                    "aisle_orchestrator.recovery_reconciled_to_resolved job_id=%s asset_id=%s",
                    job_id,
                    state.asset_id,
                )
                continue
            expected_version = int(state.version or 1)
            owner_token = state.worker_token
            state.status = JobAssetProcessingStatus.PENDING
            state.error_code = "ABANDONED_PROCESSING_RECOVERED"
            state.error_message = f"Recovered after {age_s}s without progress"
            state.updated_at = now
            state.version = expected_version + 1
            try:
                self._state_repo.save_with_ownership(
                    state, expected_version=expected_version, worker_token=owner_token
                )
            except AssetProcessingStateConcurrencyError:
                logger.info(
                    "aisle_orchestrator.recovery_lost_race job_id=%s asset_id=%s",
                    job_id,
                    state.asset_id,
                )
                continue
            recovered.append(state.asset_id)
            logger.warning(
                "aisle_orchestrator.asset_state_recovered job_id=%s asset_id=%s "
                "age_seconds=%s recovery_reason=%s previous_worker_token=%s",
                job_id,
                state.asset_id,
                age_s,
                state.error_code,
                owner_token,
            )
        return recovered

    def _close_started_attempts_for_assets(
        self, job_id: str, asset_ids: Sequence[str], now: datetime
    ) -> None:
        if not asset_ids:
            return
        wanted = set(asset_ids)
        for attempt in self._attempt_repo.list_started_by_job(job_id):
            if attempt.asset_id not in wanted:
                continue
            attempt.status = ProcessingAttemptStatus.FAILED_TECHNICAL
            attempt.finished_at = now
            attempt.error_code = "ABANDONED_PROCESSING_RECOVERED"
            attempt.error_message = "Closed while recovering an abandoned PROCESSING asset state"
            attempt.updated_at = now
            self._attempt_repo.save(attempt)

    def _recover_started_batch_attempts(
        self, job_id: str, strategy: str, execution_scope: str, now: datetime
    ) -> None:
        cutoff = now - timedelta(seconds=self._abandoned_ttl)
        for attempt in self._batch_attempt_repo.get_started_by_job(
            job_id, strategy, execution_scope
        ):
            ref = attempt.started_at or attempt.created_at
            if ref is not None and ref > cutoff:
                continue
            self._batch_attempt_repo.finalize(
                attempt.id,
                status=BatchProcessingAttemptStatus.FAILED_TECHNICAL,
                now=now,
                error_code="ABANDONED_BATCH_RECOVERED",
                error_message="Closed while recovering an abandoned batch attempt",
            )
            logger.warning(
                "aisle_orchestrator.recovered_abandoned_batch_attempt job_id=%s "
                "batch_attempt_id=%s strategy=%s execution_scope=%s",
                job_id,
                attempt.id,
                strategy,
                execution_scope,
            )

    def _recover_all(self, job_id: str, strategy_key: str, execution_scope: str) -> None:
        now = self._clock.now()
        recovered_asset_ids = self.recover_abandoned_processing(job_id)
        self._close_started_attempts_for_assets(job_id, recovered_asset_ids, now)
        self._lease_repo.recover_expired(now=now, limit=self._lease_recovery_sweep_limit)
        self._recover_started_batch_attempts(job_id, strategy_key, execution_scope, now)

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def process_with_legacy_batch(
        self,
        *,
        job: Job,
        aisle: Aisle,
        assets: Sequence[SourceAsset],
        batch_runner: LegacyBatchRunner,
        pipeline_enabled: bool,
        orchestrator_enabled: bool,
        is_cancelled: Callable[[], bool],
        worker_token: str,
    ) -> AisleOrchestratorOutcome:
        strategy_key = self._resolver.resolve_strategy_key(
            job,
            pipeline_enabled=pipeline_enabled,
            orchestrator_enabled=orchestrator_enabled,
        )
        execution_scope = ExecutionScope.AISLE_BATCH.value

        self.ensure_asset_states(job, assets)
        self._recover_all(job.id, strategy_key, execution_scope)

        if is_cancelled():
            return self._cancel_before_lease(job, strategy_key)

        lease = self._lease_repo.try_acquire_lease(
            job_id=job.id,
            strategy=strategy_key,
            execution_scope=execution_scope,
            worker_token=worker_token,
            now=self._clock.now(),
            lease_duration_seconds=self._lease_duration_seconds,
        )
        if lease is None:
            logger.info(
                "aisle_orchestrator.batch_lease_not_acquired job_id=%s strategy=%s "
                "execution_scope=%s worker_token=%s",
                job.id,
                strategy_key,
                execution_scope,
                worker_token,
            )
            progress = self._state_repo.aggregate_progress(job.id)
            return AisleOrchestratorOutcome(
                legacy=LegacyBatchOutcome(
                    ok=False,
                    error_message="BATCH_LEASE_NOT_ACQUIRED",
                    skipped_busy=True,
                ),
                progress=progress,
                strategy_key=strategy_key,
            )

        logger.info(
            "aisle_orchestrator.batch_lease_acquired job_id=%s lease_id=%s strategy=%s "
            "execution_scope=%s worker_token=%s",
            job.id,
            lease.id,
            strategy_key,
            execution_scope,
            worker_token,
        )

        if is_cancelled():
            self._lease_repo.release(lease.id, worker_token=worker_token, now=self._clock.now())
            return self._cancel_before_lease(job, strategy_key)

        now = self._clock.now()
        batch_attempt = self._batch_attempt_repo.create_started(
            BatchProcessingAttempt(
                id=str(uuid.uuid4()),
                job_id=job.id,
                strategy=strategy_key,
                execution_scope=execution_scope,
                status=BatchProcessingAttemptStatus.STARTED,
                created_at=now,
                updated_at=now,
                provider=job.provider_name,
                model=job.model_name,
                prompt_key=job.prompt_key,
                prompt_version=job.prompt_version,
                worker_token=worker_token,
                started_at=now,
            )
        )
        logger.info(
            "aisle_orchestrator.batch_attempt_started job_id=%s batch_attempt_id=%s "
            "strategy=%s worker_token=%s",
            job.id,
            batch_attempt.id,
            strategy_key,
            worker_token,
        )

        acquired_assets, attempts_by_asset = self._acquire_assets_and_attempts(
            job=job,
            assets=assets,
            strategy_key=strategy_key,
            execution_scope=execution_scope,
            batch_attempt_id=batch_attempt.id,
            worker_token=worker_token,
        )

        if is_cancelled():
            return self._cancel_after_acquire(
                job=job,
                lease_id=lease.id,
                batch_attempt_id=batch_attempt.id,
                attempts_by_asset=attempts_by_asset,
                strategy_key=strategy_key,
                worker_token=worker_token,
            )

        try:
            outcome = self._legacy.process_aisle_batch(
                job=job, assets=acquired_assets, batch_runner=batch_runner
            )
        except PipelineCancellationRequestedError:
            # Unlike a technical failure, a cooperative-cancel checkpoint inside the legacy
            # pipeline is *not* ours to swallow: V3JobExecutor has its own
            # PipelineCancellationRequestedError handler (cancellation coordinator) that must
            # still run to record the cancellation on the job/aisle, so this one re-raises
            # after releasing our own bookkeeping (lease, batch attempt, per-asset states).
            logger.info(
                "aisle_orchestrator.batch_runner_cancelled job_id=%s strategy=%s",
                job.id,
                strategy_key,
            )
            self._cancel_after_acquire(
                job=job,
                lease_id=lease.id,
                batch_attempt_id=batch_attempt.id,
                attempts_by_asset=attempts_by_asset,
                strategy_key=strategy_key,
                worker_token=worker_token,
            )
            raise
        except Exception as exc:
            # Re-raised deliberately: the batch_runner (legacy pipeline + finalization) is
            # responsible for its own job/aisle failure reporting, but that reporting can
            # itself fail (see JobFinalizationTracker.report_finalization_failure, which
            # logs CRITICAL and re-raises rather than swallowing). The caller (V3JobExecutor)
            # owns the top-level "unexpected failure" handler, which re-fetches the job before
            # writing FAILED — so a prior failed write here does not repeat itself there. Our
            # own bookkeeping (lease, batch attempt, per-asset states/attempts) is still closed
            # out below before propagating.
            logger.exception(
                "aisle_orchestrator.batch_runner_exception job_id=%s strategy=%s",
                job.id,
                strategy_key,
            )
            self._finalize_on_exception(
                job=job,
                lease_id=lease.id,
                batch_attempt_id=batch_attempt.id,
                attempts_by_asset=attempts_by_asset,
                strategy_key=strategy_key,
                worker_token=worker_token,
                error_message=str(exc),
            )
            raise

        finish_now = self._clock.now()
        if outcome.ok and not outcome.cancelled:
            self._batch_attempt_repo.finalize(
                batch_attempt.id, status=BatchProcessingAttemptStatus.SUCCEEDED, now=finish_now
            )
            self._lease_repo.complete(lease.id, worker_token=worker_token, now=finish_now)
        elif outcome.cancelled:
            self._batch_attempt_repo.finalize(
                batch_attempt.id, status=BatchProcessingAttemptStatus.CANCELLED, now=finish_now
            )
            self._lease_repo.release(lease.id, worker_token=worker_token, now=finish_now)
        else:
            self._batch_attempt_repo.finalize(
                batch_attempt.id,
                status=BatchProcessingAttemptStatus.FAILED_TECHNICAL,
                now=finish_now,
                error_code="LEGACY_BATCH_FAILED",
                error_message=outcome.error_message,
            )
            self._lease_repo.fail(
                lease.id,
                worker_token=worker_token,
                now=finish_now,
                error_message=outcome.error_message,
            )

        self._synthesize_after_batch(
            job=job,
            aisle=aisle,
            assets=acquired_assets,
            outcome=outcome,
            attempts_by_asset=attempts_by_asset,
            strategy_key=strategy_key,
        )
        if outcome.cancelled:
            self._cancel_pending(job.id)

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

    # ------------------------------------------------------------------
    # Phase 3 — CODE_SCAN per-asset processing (no lease, no LLM)
    # ------------------------------------------------------------------

    def process_with_code_scan(
        self,
        *,
        job: Job,
        aisle: Aisle,
        assets: Sequence[SourceAsset],
        pipeline_enabled: bool,
        orchestrator_enabled: bool,
        is_cancelled: Callable[[], bool],
        worker_token: str,
        code_scan_processing_enabled: bool = True,
        internal_ocr_processing_enabled: bool = False,
        merge_progress: Callable[[AssetProgressCounts], None] | None = None,
        progress_merge_interval: int = 10,
    ) -> CodeScanAisleOutcome:
        """Process each PENDING asset as an isolated SINGLE_ASSET code scan.

        No :class:`JobProcessingLease` is acquired (physical unit is one asset, not the
        whole aisle) and the legacy LLM batch runner is never invoked. Concurrency is bounded
        by ``code_scan_concurrency`` (default 1). Asset-level ownership (``worker_token`` +
        optimistic version) still guards against two workers finalizing the same asset.
        """
        # C — the code-scan path must never run without both collaborators: a missing strategy
        # or persister would silently drop RESOLVED_INTERNAL positions (data loss).
        if self._code_scan_strategy is None or self._result_persister is None:
            raise CodeScanPipelineMisconfiguredError(
                "process_with_code_scan requires both a code_scan_strategy and a result_persister "
                f"(strategy={'set' if self._code_scan_strategy else 'missing'}, "
                f"persister={'set' if self._result_persister else 'missing'})"
            )

        strategy_key = self._resolver.resolve_strategy_key(
            job,
            pipeline_enabled=pipeline_enabled,
            orchestrator_enabled=orchestrator_enabled,
            code_scan_processing_enabled=code_scan_processing_enabled,
            internal_ocr_processing_enabled=internal_ocr_processing_enabled,
        )

        self.ensure_asset_states(job, assets, execution_scope=ExecutionScope.SINGLE_ASSET)
        now = self._clock.now()
        recovered = self.recover_abandoned_processing(job.id)
        self._close_started_attempts_for_assets(job.id, recovered, now)

        if self._apply_authoritative_local is not None:
            try:
                self._apply_authoritative_local.apply_for_job(
                    job=job,
                    aisle_id=aisle.id,
                    inventory_id=aisle.inventory_id,
                    assets=list(assets),
                )
            except Exception:
                logger.exception(
                    "authoritative_local.apply_batch_failed job_id=%s aisle_id=%s",
                    job.id,
                    aisle.id,
                )

        if is_cancelled():
            return self._code_scan_cancel(job, strategy_key)

        processor = CodeScanAssetProcessor(
            state_repo=self._state_repo,
            attempt_repo=self._attempt_repo,
            image_orchestrator=self._image_orch,
            code_scan_strategy=self._code_scan_strategy,
            result_persister=self._result_persister,
            clock=self._clock,
            attempts_enabled=self._attempts_enabled,
            reconciler=self._reconciler,
            external_fallback=self._external_fallback,
        )

        lock = threading.Lock()
        errors: list[str] = []
        processed_counter = {"n": 0}

        def _maybe_merge_progress(force: bool = False) -> None:
            if merge_progress is None:
                return
            with lock:
                processed_counter["n"] += 0 if force else 1
                due = force or (processed_counter["n"] % max(1, progress_merge_interval) == 0)
            if due:
                try:
                    merge_progress(self._state_repo.aggregate_progress(job.id))
                except Exception:
                    global asset_progress_publish_failed_total
                    asset_progress_publish_failed_total += 1
                    logger.exception(
                        "aisle_orchestrator.code_scan_progress_merge_failed job_id=%s "
                        "publish_failed_total=%s",
                        job.id,
                        asset_progress_publish_failed_total,
                    )

        eligible = [
            asset
            for asset in assets
            if not self._image_orch.is_terminal(
                self._state_repo.get_by_job_and_asset(job.id, asset.id)
            )
        ]
        assets_eligible = len(eligible)
        assets_started_box = {"n": 0}

        def _process_one(asset: SourceAsset) -> None:
            if is_cancelled():
                return
            with lock:
                assets_started_box["n"] += 1
            outcome = processor.process_asset(
                job=job,
                aisle=aisle,
                asset=asset,
                strategy_key=strategy_key,
                worker_token=worker_token,
            )
            if outcome.error:
                with lock:
                    errors.append(outcome.error)
            _maybe_merge_progress()

        if self._code_scan_concurrency <= 1:
            for asset in eligible:
                if is_cancelled():
                    break
                _process_one(asset)
        else:
            with ThreadPoolExecutor(max_workers=self._code_scan_concurrency) as executor:
                list(executor.map(_process_one, eligible))

        with lock:
            assets_started = int(assets_started_box["n"])

        if (
            strategy_key == "CODE_SCAN"
            and assets_eligible > 0
            and assets_started == 0
            and not is_cancelled()
        ):
            progress = self._state_repo.aggregate_progress(job.id)
            logger.error(
                "aisle_orchestrator.code_scan_asset_loop_not_executed job_id=%s "
                "assets_eligible=%s assets_started=%s",
                job.id,
                assets_eligible,
                assets_started,
            )
            return CodeScanAisleOutcome(
                ok=False,
                cancelled=False,
                progress=progress,
                strategy_key=strategy_key,
                job_outcome=CodeScanJobOutcome.FAILED,
                error_message="CODE_SCAN_ASSET_LOOP_NOT_EXECUTED",
                assets_eligible=assets_eligible,
                assets_started=assets_started,
            )

        cancelled = is_cancelled()
        if cancelled:
            self._cancel_pending(job.id)

        _maybe_merge_progress(force=True)
        progress = self._state_repo.aggregate_progress(job.id)
        job_outcome = decide_code_scan_job_outcome(
            progress=progress, cancelled=cancelled, infrastructure_error=None
        )
        logger.info(
            "aisle_orchestrator.code_scan_complete job_id=%s strategy=%s job_outcome=%s "
            "total=%s resolved=%s unrecognized=%s failed=%s manual_review=%s cancelled=%s "
            "assets_eligible=%s assets_started=%s",
            job.id,
            strategy_key,
            job_outcome.value,
            progress.total,
            progress.resolved,
            progress.unrecognized,
            progress.failed,
            progress.manual_review,
            cancelled,
            assets_eligible,
            assets_started,
        )
        return CodeScanAisleOutcome(
            ok=job_outcome
            in (CodeScanJobOutcome.SUCCEEDED, CodeScanJobOutcome.PARTIALLY_COMPLETED),
            cancelled=cancelled,
            progress=progress,
            strategy_key=strategy_key,
            job_outcome=job_outcome,
            error_message="; ".join(errors) if errors else None,
            assets_eligible=assets_eligible,
            assets_started=assets_started,
        )

    def process_with_internal_ocr(
        self,
        *,
        job: Job,
        aisle: Aisle,
        assets: Sequence[SourceAsset],
        pipeline_enabled: bool,
        orchestrator_enabled: bool,
        is_cancelled: Callable[[], bool],
        worker_token: str,
        internal_ocr_processing_enabled: bool = True,
        merge_progress: Callable[[AssetProgressCounts], None] | None = None,
        progress_merge_interval: int = 10,
    ) -> CodeScanAisleOutcome:
        """Phase 4 — process each PENDING asset via local INTERNAL_OCR (no LLM).

        Reuses the CODE_SCAN SINGLE_ASSET run loop, persister, reconciler, and job-outcome
        policy. The injected ``code_scan_strategy`` collaborator must be an
        :class:`InternalOcrProcessingStrategy` (duck-typed ``process(context, asset)``).
        """
        if self._code_scan_strategy is None or self._result_persister is None:
            raise CodeScanPipelineMisconfiguredError(
                "process_with_internal_ocr requires both an OCR strategy and a result_persister "
                f"(strategy={'set' if self._code_scan_strategy else 'missing'}, "
                f"persister={'set' if self._result_persister else 'missing'})"
            )
        return self.process_with_code_scan(
            job=job,
            aisle=aisle,
            assets=assets,
            pipeline_enabled=pipeline_enabled,
            orchestrator_enabled=orchestrator_enabled,
            is_cancelled=is_cancelled,
            worker_token=worker_token,
            code_scan_processing_enabled=True,
            internal_ocr_processing_enabled=internal_ocr_processing_enabled,
            merge_progress=merge_progress,
            progress_merge_interval=progress_merge_interval,
        )

    def _code_scan_cancel(self, job: Job, strategy_key: str) -> CodeScanAisleOutcome:
        self._cancel_pending(job.id)
        progress = self._state_repo.aggregate_progress(job.id)
        return CodeScanAisleOutcome(
            ok=False,
            cancelled=True,
            progress=progress,
            strategy_key=strategy_key,
            job_outcome=CodeScanJobOutcome.CANCELLED,
        )

    # ------------------------------------------------------------------
    # Acquisition
    # ------------------------------------------------------------------

    def _acquire_assets_and_attempts(
        self,
        *,
        job: Job,
        assets: Sequence[SourceAsset],
        strategy_key: str,
        execution_scope: str,
        batch_attempt_id: str,
        worker_token: str,
    ) -> tuple[list[SourceAsset], dict[str, ProcessingAttempt]]:
        acquired: list[SourceAsset] = []
        attempts_by_asset: dict[str, ProcessingAttempt] = {}
        now = self._clock.now()
        for asset in assets:
            state = self._state_repo.get_by_job_and_asset(job.id, asset.id)
            if state is None or self._image_orch.is_terminal(state):
                continue
            acquired_state = self._image_orch.acquire_for_processing(
                job_id=job.id,
                asset_id=asset.id,
                strategy=strategy_key,
                worker_token=worker_token,
            )
            if acquired_state is None:
                logger.info(
                    "aisle_orchestrator.skip_busy job_id=%s asset_id=%s",
                    job.id,
                    asset.id,
                )
                continue
            acquired.append(asset)
            if self._attempts_enabled:
                attempt = self._attempt_repo.create_next_attempt(
                    job_id=job.id,
                    asset_id=asset.id,
                    strategy=strategy_key,
                    status=ProcessingAttemptStatus.STARTED,
                    now=now,
                    provider=job.provider_name,
                    model=job.model_name,
                    execution_scope=execution_scope,
                    configuration_snapshot_version=job.configuration_snapshot_version,
                    parent_batch_attempt_id=batch_attempt_id,
                    batch_execution_id=batch_attempt_id,
                    worker_token=worker_token,
                    logical_asset_attempt=True,
                )
                attempts_by_asset[asset.id] = attempt
        return acquired, attempts_by_asset

    # ------------------------------------------------------------------
    # Synthesis (coverage resolver drives per-asset outcome)
    # ------------------------------------------------------------------

    def _synthesize_after_batch(
        self,
        *,
        job: Job,
        aisle: Aisle,
        assets: Sequence[SourceAsset],
        outcome: LegacyBatchOutcome,
        attempts_by_asset: dict[str, ProcessingAttempt],
        strategy_key: str,
    ) -> None:
        for asset in assets:
            state = self._state_repo.get_by_job_and_asset(job.id, asset.id)
            if state is None or self._image_orch.is_terminal(state):
                continue
            attempt = attempts_by_asset.get(asset.id)

            if outcome.cancelled:
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
            else:
                result = self._build_result_from_coverage(
                    job=job, aisle=aisle, asset=asset, strategy_key=strategy_key
                )

            try:
                self._image_orch.finalize_from_result(
                    state=state, attempt=attempt, result=result, strategy=strategy_key
                )
            except AssetProcessingStateConcurrencyError:
                logger.warning(
                    "aisle_orchestrator.finalize_lost_race job_id=%s asset_id=%s",
                    job.id,
                    asset.id,
                )

    def _build_result_from_coverage(
        self, *, job: Job, aisle: Aisle, asset: SourceAsset, strategy_key: str
    ) -> ImageProcessingResult:
        coverage = self._coverage.resolve(job_id=job.id, aisle_id=aisle.id, asset_id=asset.id)
        status = _COVERAGE_TO_RESULT_STATUS[coverage]
        if coverage == AssetResultCoverageStatus.RESOLVED:
            warnings = [
                "Logical asset result synthesized from AISLE_BATCH legacy coverage; "
                "provider did not process this asset as an isolated request."
            ]
            error_code = None
            error_message = None
        elif coverage == AssetResultCoverageStatus.PENDING_RECONCILIATION:
            warnings = []
            error_code = "COVERAGE_AMBIGUOUS"
            error_message = (
                "Coverage signals inconclusive after AISLE_BATCH legacy run; "
                "needs manual reconciliation."
            )
        else:
            warnings = ["No position/evidence linked for asset after AISLE_BATCH legacy run."]
            error_code = None
            error_message = None
        return ImageProcessingResult(
            job_id=job.id,
            asset_id=asset.id,
            status=status,
            processing_mode=job.identification_mode.value,
            resolved_by=strategy_key,
            error_code=error_code,
            error_message=error_message,
            execution_scope=ExecutionScope.AISLE_BATCH,
            provider_name=job.provider_name,
            model_name=job.model_name,
            warnings=warnings,
        )

    # ------------------------------------------------------------------
    # Cancellation / failure cleanup
    # ------------------------------------------------------------------

    def _cancel_before_lease(self, job: Job, strategy_key: str) -> AisleOrchestratorOutcome:
        self._cancel_pending(job.id)
        progress = self._state_repo.aggregate_progress(job.id)
        return AisleOrchestratorOutcome(
            legacy=LegacyBatchOutcome(ok=False, cancelled=True),
            progress=progress,
            strategy_key=strategy_key,
        )

    def _cancel_after_acquire(
        self,
        *,
        job: Job,
        lease_id: str,
        batch_attempt_id: str,
        attempts_by_asset: dict[str, ProcessingAttempt],
        strategy_key: str,
        worker_token: str,
    ) -> AisleOrchestratorOutcome:
        now = self._clock.now()
        for asset_id, attempt in attempts_by_asset.items():
            state = self._state_repo.get_by_job_and_asset(job.id, asset_id)
            if state is None or self._image_orch.is_terminal(state):
                continue
            try:
                self._image_orch.mark_cancelled(state, attempt)
            except AssetProcessingStateConcurrencyError:
                logger.warning(
                    "aisle_orchestrator.cancel_lost_race job_id=%s asset_id=%s", job.id, asset_id
                )
        self._batch_attempt_repo.finalize(
            batch_attempt_id, status=BatchProcessingAttemptStatus.CANCELLED, now=now
        )
        self._lease_repo.release(lease_id, worker_token=worker_token, now=now)
        self._cancel_pending(job.id)
        progress = self._state_repo.aggregate_progress(job.id)
        return AisleOrchestratorOutcome(
            legacy=LegacyBatchOutcome(ok=False, cancelled=True),
            progress=progress,
            strategy_key=strategy_key,
        )

    def _finalize_on_exception(
        self,
        *,
        job: Job,
        lease_id: str,
        batch_attempt_id: str,
        attempts_by_asset: dict[str, ProcessingAttempt],
        strategy_key: str,
        worker_token: str,
        error_message: str,
    ) -> None:
        now = self._clock.now()
        for asset_id, attempt in attempts_by_asset.items():
            state = self._state_repo.get_by_job_and_asset(job.id, asset_id)
            if state is None or self._image_orch.is_terminal(state):
                continue
            result = ImageProcessingResult(
                job_id=job.id,
                asset_id=asset_id,
                status=ImageResultStatus.FAILED_TECHNICAL,
                processing_mode=job.identification_mode.value,
                resolved_by=strategy_key,
                error_code="BATCH_RUNNER_EXCEPTION",
                error_message=error_message,
                execution_scope=ExecutionScope.AISLE_BATCH,
                provider_name=job.provider_name,
                model_name=job.model_name,
            )
            try:
                self._image_orch.finalize_from_result(
                    state=state, attempt=attempt, result=result, strategy=strategy_key
                )
            except AssetProcessingStateConcurrencyError:
                logger.warning(
                    "aisle_orchestrator.finalize_lost_race job_id=%s asset_id=%s",
                    job.id,
                    asset_id,
                )
        self._batch_attempt_repo.finalize(
            batch_attempt_id,
            status=BatchProcessingAttemptStatus.FAILED_TECHNICAL,
            now=now,
            error_code="BATCH_RUNNER_EXCEPTION",
            error_message=error_message,
        )
        self._lease_repo.fail(
            lease_id, worker_token=worker_token, now=now, error_message=error_message
        )

    def _cancel_pending(self, job_id: str) -> None:
        for state in self._state_repo.list_by_job(job_id):
            if state.status in (
                JobAssetProcessingStatus.PENDING,
                JobAssetProcessingStatus.PROCESSING,
            ):
                try:
                    self._image_orch.mark_cancelled(state, None)
                except AssetProcessingStateConcurrencyError:
                    logger.warning(
                        "aisle_orchestrator.cancel_pending_lost_race job_id=%s asset_id=%s",
                        job_id,
                        state.asset_id,
                    )
