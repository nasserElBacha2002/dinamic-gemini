"""
Job and aisle lifecycle transitions for v3 ``process_aisle`` execution (Phase 2 split).

Phase 3.2: finalization progress metadata and specific error taxonomy for post-pipeline steps.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from src.application.ports.clock import Clock
from src.application.ports.operational_job_promotion import PromotionOutcome
from src.application.ports.repositories import AisleRepository, InventoryRepository, JobRepository
from src.application.services.inventory_status_reconciler import InventoryStatusReconciler
from src.application.services.operational_result_promotion_service import (
    OperationalResultPromotionService,
)
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.inventory.entities import InventoryProcessingMode
from src.domain.jobs.claim import JobClaimResult
from src.domain.jobs.entities import Job, JobStatus
from src.domain.jobs.finalization import (
    CurrentFinalizationStep,
    FinalizationErrorCode,
    FinalizationStatus,
    LastCompletedFinalizationStep,
    is_hard_promotion_failure,
)
from src.domain.jobs.lease import (
    JobLease,
    JobLeaseLostError,
    LeaseRenewalOutcome,
    LeaseRenewalResult,
    LeaseWriteOutcome,
)
from src.infrastructure.pipeline.job_finalization_tracker import (
    JobFinalizationTracker,
    report_finalization_failure,
)
from src.infrastructure.pipeline.worker_durable_artifact_publisher import (
    merge_durable_into_result_json,
)
from src.pipeline.errors import PipelineCancellationRequestedError
from src.pipeline.execution_log import ExecutionLogWriter
from src.pipeline.run_metadata import (
    RUN_METADATA_KEY_LLM_COST_SNAPSHOT,
    RUN_METADATA_KEY_RUN_AUDIT_SNAPSHOT,
    RUN_METADATA_KEY_VISUAL_REFERENCE_CONTEXT,
    default_empty_block,
)

logger = logging.getLogger(__name__)


class V3JobExecutionStateService:
    """Mutates Job + Aisle domain state and inventory reconciliation for worker execution."""

    def __init__(
        self,
        *,
        job_repo: JobRepository,
        aisle_repo: AisleRepository,
        inventory_repo: InventoryRepository,
        clock: Clock,
        inventory_status_reconciler: InventoryStatusReconciler,
        operational_promotion_service: OperationalResultPromotionService | None = None,
    ) -> None:
        self._job_repo = job_repo
        self._aisle_repo = aisle_repo
        self._inventory_repo = inventory_repo
        self._clock = clock
        self._inventory_status_reconciler = inventory_status_reconciler
        self._operational_promotion_service = operational_promotion_service

    def reconcile_inventory_for_aisle(self, aisle: Aisle) -> None:
        self._inventory_status_reconciler.reconcile(aisle.inventory_id)

    def mark_running(
        self,
        job_id: str,
        aisle: Aisle,
        now,
        *,
        claim_owner_id: str,
        lease_duration_seconds: int = 60,
    ) -> JobClaimResult:
        """Atomic STARTING → RUNNING claim + aisle PROCESSING (Phase 1 + Phase 3 lease).

        Requires a non-empty ``claim_owner_id`` unique to this worker invocation.
        Callers must only execute the pipeline when ``result.may_execute`` is True.
        """
        from src.domain.jobs.claim import JobClaimOutcome, JobClaimResult

        if not isinstance(claim_owner_id, str) or not claim_owner_id.strip():
            raise ValueError("claim_owner_id is required for mark_running")

        from src.infrastructure.repositories.memory_job_repository import MemoryJobRepository

        if isinstance(self._job_repo, MemoryJobRepository):
            self._job_repo.bind_aisle_repository(self._aisle_repo)

        result = self._job_repo.try_claim_starting_to_running(
            job_id,
            now=now,
            claim_owner_id=claim_owner_id.strip(),
            aisle_id=aisle.id,
            lease_duration_seconds=lease_duration_seconds,
        )
        if not isinstance(result, JobClaimResult):
            raise TypeError(
                f"try_claim_starting_to_running must return JobClaimResult, got {type(result)!r}"
            )

        if not result.may_execute:
            logger.info(
                "event=job_claim_rejected job_id=%s aisle_id=%s claim_owner_id=%s reason=%s "
                "current_status=%s current_owner=%s",
                job_id,
                aisle.id,
                claim_owner_id,
                result.reason,
                result.previous_status,
                getattr(result.job, "claim_owner_id", None) if result.job else None,
            )
            return result

        if result.aisle_transition_applied or aisle.status != AisleStatus.PROCESSING:
            refreshed = self._aisle_repo.get_by_id(aisle.id)
            if refreshed is not None:
                aisle.status = refreshed.status
                aisle.updated_at = refreshed.updated_at
                aisle.error_code = refreshed.error_code
                aisle.error_message = refreshed.error_message
                aisle.retryable = refreshed.retryable
            elif aisle.status != AisleStatus.PROCESSING:
                aisle.mark_processing(now)
                self._aisle_repo.save(aisle)

        if result.outcome == JobClaimOutcome.ACQUIRED:
            logger.info(
                "event=job_claim_acquired job_id=%s aisle_id=%s claim_owner_id=%s "
                "previous_status=%s new_status=running attempt=%s",
                job_id,
                aisle.id,
                claim_owner_id,
                result.previous_status,
                getattr(result.job, "attempt_count", None) if result.job else None,
            )

        self.reconcile_inventory_for_aisle(aisle)
        return result

    def finalize_success(
        self,
        job_id: str,
        aisle: Aisle,
        report_path: Path,
        *,
        tracker: JobFinalizationTracker,
        run_metadata: dict | None = None,
        durable_artifacts: dict[str, dict[str, Any]] | None = None,
        lease: JobLease | None = None,
    ) -> None:
        """Terminal success steps after durable artifacts — records finalization progress per step."""
        completion_now = self._clock.now()
        if lease is not None:
            assert_result = self._job_repo.assert_lease(lease, now=completion_now)
            if not assert_result.applied:
                raise JobLeaseLostError(
                    "Lease lost before finalization",
                    job_id=job_id,
                    owner_id=lease.owner_id,
                    fencing_token=lease.fencing_token,
                    reason=assert_result.reason,
                )
        tracker.set_current_step(CurrentFinalizationStep.TERMINALIZE_JOB)
        try:
            self._terminalize_job_row(
                job_id,
                report_path,
                completion_now=completion_now,
                run_metadata=run_metadata,
                durable_artifacts=durable_artifacts,
                lease=lease,
            )
        except JobLeaseLostError:
            # Another worker may own the job — do not fail aisle/job.
            raise
        except Exception as exc:
            try:
                report_finalization_failure(
                    tracker,
                    error_code=FinalizationErrorCode.JOB_TERMINALIZATION_FAILED,
                    current_step=CurrentFinalizationStep.TERMINALIZE_JOB,
                    message=f"Job terminalization failed: {exc}",
                    metadata={"exception_type": type(exc).__name__},
                    job_status=JobStatus.FAILED,
                )
            except Exception:
                logger.error(
                    "finalization_job_metadata_unavailable job_id=%s step=terminalize_job",
                    job_id,
                )
            self._fail_aisle_for_finalization(
                aisle,
                failing_job_id=job_id,
                error_code=FinalizationErrorCode.JOB_TERMINALIZATION_FAILED.value,
                message=str(exc),
            )
            raise

        tracker.record_step_completed(LastCompletedFinalizationStep.JOB_TERMINALIZED)
        tracker.set_current_step(CurrentFinalizationStep.PROMOTE_OPERATIONAL_RESULT)

        try:
            promotion_outcome = self._promote_operational_result(job_id, aisle)
        except Exception as exc:
            try:
                report_finalization_failure(
                    tracker,
                    error_code=FinalizationErrorCode.OPERATIONAL_PROMOTION_FAILED,
                    current_step=CurrentFinalizationStep.PROMOTE_OPERATIONAL_RESULT,
                    message=f"Operational promotion failed: {exc}",
                    metadata={"exception_type": type(exc).__name__},
                    job_status=JobStatus.SUCCEEDED,
                )
            except Exception:
                logger.error(
                    "finalization_job_metadata_unavailable job_id=%s step=promote_operational_result",
                    job_id,
                )
            self._fail_aisle_for_finalization(
                aisle,
                failing_job_id=job_id,
                error_code=FinalizationErrorCode.OPERATIONAL_PROMOTION_FAILED.value,
                message=str(exc),
            )
            raise

        if is_hard_promotion_failure(promotion_outcome):
            msg = f"Operational promotion rejected: {promotion_outcome}"
            try:
                report_finalization_failure(
                    tracker,
                    error_code=FinalizationErrorCode.OPERATIONAL_PROMOTION_FAILED,
                    current_step=CurrentFinalizationStep.PROMOTE_OPERATIONAL_RESULT,
                    message=msg,
                    metadata={"promotion_outcome": promotion_outcome},
                    job_status=JobStatus.SUCCEEDED,
                )
            except Exception:
                logger.error(
                    "finalization_job_metadata_unavailable job_id=%s step=promote_operational_result",
                    job_id,
                )
            self._fail_aisle_for_finalization(
                aisle,
                failing_job_id=job_id,
                error_code=FinalizationErrorCode.OPERATIONAL_PROMOTION_FAILED.value,
                message=msg,
            )
            raise RuntimeError(msg)

        tracker.record_step_completed(LastCompletedFinalizationStep.OPERATIONAL_RESULT_PROMOTED)
        tracker.set_current_step(CurrentFinalizationStep.UPDATE_AISLE)

        try:
            aisle.mark_processed(completion_now)
            self._aisle_repo.save(aisle)
        except Exception as exc:
            try:
                report_finalization_failure(
                    tracker,
                    error_code=FinalizationErrorCode.AISLE_RECONCILIATION_FAILED,
                    current_step=CurrentFinalizationStep.UPDATE_AISLE,
                    message=f"Aisle update failed: {exc}",
                    metadata={"exception_type": type(exc).__name__},
                    job_status=JobStatus.SUCCEEDED,
                )
            except Exception:
                logger.error(
                    "finalization_job_metadata_unavailable job_id=%s step=update_aisle",
                    job_id,
                )
            self._fail_aisle_for_finalization(
                aisle,
                failing_job_id=job_id,
                error_code=FinalizationErrorCode.AISLE_RECONCILIATION_FAILED.value,
                message=str(exc),
            )
            raise

        tracker.record_step_completed(LastCompletedFinalizationStep.AISLE_UPDATED)
        tracker.set_current_step(CurrentFinalizationStep.RECONCILE_INVENTORY)

        try:
            self.reconcile_inventory_for_aisle(aisle)
        except Exception as exc:
            try:
                report_finalization_failure(
                    tracker,
                    error_code=FinalizationErrorCode.INVENTORY_RECONCILIATION_FAILED,
                    current_step=CurrentFinalizationStep.RECONCILE_INVENTORY,
                    message=f"Inventory reconciliation failed: {exc}",
                    metadata={"exception_type": type(exc).__name__},
                    job_status=JobStatus.SUCCEEDED,
                )
            except Exception:
                logger.error(
                    "finalization_job_metadata_unavailable job_id=%s step=reconcile_inventory",
                    job_id,
                )
            self._fail_aisle_for_finalization(
                aisle,
                failing_job_id=job_id,
                error_code=FinalizationErrorCode.INVENTORY_RECONCILIATION_FAILED.value,
                message=str(exc),
            )
            raise

        tracker.record_step_completed(LastCompletedFinalizationStep.INVENTORY_RECONCILED)
        tracker.complete()

    def mark_success(
        self,
        job_id: str,
        aisle: Aisle,
        report_path: Path,
        *,
        run_metadata: dict | None = None,
        durable_artifacts: dict[str, dict[str, Any]] | None = None,
        tracker: JobFinalizationTracker | None = None,
    ) -> None:
        """Backward-compatible entry; prefer :meth:`finalize_success` with an active tracker."""
        if tracker is not None:
            self.finalize_success(
                job_id,
                aisle,
                report_path,
                tracker=tracker,
                run_metadata=run_metadata,
                durable_artifacts=durable_artifacts,
            )
            return
        completion_now = self._clock.now()
        self._terminalize_job_row(
            job_id,
            report_path,
            completion_now=completion_now,
            run_metadata=run_metadata,
            durable_artifacts=durable_artifacts,
        )
        self._promote_operational_result(job_id, aisle)
        aisle.mark_processed(completion_now)
        self._aisle_repo.save(aisle)
        self.reconcile_inventory_for_aisle(aisle)
        from src.application.services.preliminary_reconciliation_enqueue_hook import (
            try_enqueue_preliminary_reconciliations,
        )

        try_enqueue_preliminary_reconciliations(
            job_id=job_id,
            aisle_id=aisle.id,
            inventory_id=aisle.inventory_id,
        )

    def finalize_code_scan_success(
        self, job_id: str, aisle: Aisle, *, lease: JobLease | None = None
    ) -> None:
        """Phase 3 lightweight finalize for CODE_SCAN jobs (no LLM pipeline report).

        Positions are already persisted per asset by the code-scan persister. This marks the
        job SUCCEEDED, promotes the operational result for production inventories, marks the
        aisle processed, and reconciles inventory — without a durable pipeline report or LLM
        artifacts. ``result_json`` keys already merged by the worker (e.g. ``asset_progress``)
        are preserved.

        Refuses FAILED → SUCCEEDED (watchdog / concurrent terminal wins).
        """
        completion_now = self._clock.now()
        if lease is not None:
            assert_result = self._job_repo.assert_lease(lease, now=completion_now)
            if not assert_result.applied:
                raise JobLeaseLostError(
                    "Lease lost before code_scan finalization",
                    job_id=job_id,
                    owner_id=lease.owner_id,
                    fencing_token=lease.fencing_token,
                    reason=assert_result.reason,
                )
        job = self.try_transition_to_succeeded(job_id)
        if job is None:
            raise RuntimeError(
                f"Job not eligible for code_scan success finalization: {job_id}"
            )
        job.status = JobStatus.SUCCEEDED
        job.updated_at = completion_now
        job.finished_at = completion_now
        job.last_heartbeat_at = completion_now
        job.current_stage = (
            "InternalOcr"
            if str(getattr(job.execution_strategy, "value", job.execution_strategy)).upper()
            == "INTERNAL_OCR"
            else "CodeScan"
        )
        job.current_substep = "completed"
        result_json = dict(job.result_json or {})
        result_json["execution_strategy"] = getattr(
            job.execution_strategy, "value", str(job.execution_strategy)
        )
        job.result_json = result_json
        job.error_message = None
        job.failure_code = None
        job.failure_message = None
        job.finalization_error_code = None
        job.finalization_error_metadata = None
        if lease is not None:
            write = self._job_repo.complete_if_leased(lease, job, now=completion_now)
            if write.outcome != LeaseWriteOutcome.APPLIED:
                raise JobLeaseLostError(
                    "Lease lost during code_scan terminalization",
                    job_id=job_id,
                    owner_id=lease.owner_id,
                    fencing_token=lease.fencing_token,
                    reason=write.reason,
                )
        else:
            self._job_repo.save(job)

        self._promote_operational_result(job_id, aisle)
        aisle.mark_processed(completion_now)
        self._aisle_repo.save(aisle)
        self.reconcile_inventory_for_aisle(aisle)
        from src.application.services.preliminary_reconciliation_enqueue_hook import (
            try_enqueue_preliminary_reconciliations,
        )

        try_enqueue_preliminary_reconciliations(
            job_id=job_id,
            aisle_id=aisle.id,
            inventory_id=aisle.inventory_id,
        )

    def _terminalize_job_row(
        self,
        job_id: str,
        report_path: Path,
        *,
        completion_now,
        run_metadata: dict | None,
        durable_artifacts: dict[str, dict[str, Any]] | None,
        lease: JobLease | None = None,
    ) -> None:
        import copy

        job = self._job_repo.get_by_id(job_id)
        if job is None:
            raise RuntimeError(f"Job not found for terminalization: {job_id}")
        # Memory repos return live store references — mutate a copy so lease CAS
        # still sees RUNNING/CANCEL_REQUESTED on the persisted row.
        job = copy.deepcopy(job)
        job.status = JobStatus.SUCCEEDED
        job.updated_at = completion_now
        job.finished_at = completion_now
        job.last_heartbeat_at = completion_now
        job.current_stage = "Pipeline"
        job.current_substep = "completed"
        meta = run_metadata or {}
        vrc = meta.get(RUN_METADATA_KEY_VISUAL_REFERENCE_CONTEXT)
        job.result_json = {
            "report_path": str(report_path),
            RUN_METADATA_KEY_VISUAL_REFERENCE_CONTEXT: vrc
            if vrc is not None
            else default_empty_block(),
            "provider": meta.get("provider"),
        }
        if meta.get("prompt_key"):
            job.result_json["prompt_key"] = meta["prompt_key"]
        pvv_raw = meta.get("prompt_version")
        if not pvv_raw and meta.get("prompt_key"):
            pk = str(meta["prompt_key"]).strip()
            if pk:
                pvv_raw = f"{pk}@v2.1"
        if pvv_raw:
            pvv = str(pvv_raw).strip()
            if pvv:
                job.result_json["prompt_version"] = pvv
                job.prompt_version = pvv[:256]
        llm_cost_snapshot = meta.get(RUN_METADATA_KEY_LLM_COST_SNAPSHOT)
        if isinstance(llm_cost_snapshot, dict):
            job.result_json[RUN_METADATA_KEY_LLM_COST_SNAPSHOT] = llm_cost_snapshot
        snap = meta.get(RUN_METADATA_KEY_RUN_AUDIT_SNAPSHOT)
        if isinstance(snap, dict):
            job.result_json[RUN_METADATA_KEY_RUN_AUDIT_SNAPSHOT] = snap
        if durable_artifacts:
            merge_durable_into_result_json(job.result_json, durable_artifacts)
        job.error_message = None
        job.failure_code = None
        job.failure_message = None
        job.finalization_error_code = None
        job.finalization_error_metadata = None
        if lease is not None:
            write = self._job_repo.complete_if_leased(lease, job, now=completion_now)
            if write.outcome != LeaseWriteOutcome.APPLIED:
                raise JobLeaseLostError(
                    "Lease lost during terminalization",
                    job_id=job_id,
                    owner_id=lease.owner_id,
                    fencing_token=lease.fencing_token,
                    reason=write.reason,
                )
            return
        self._job_repo.save(job)

    def _promote_operational_result(self, job_id: str, aisle: Aisle) -> str:
        inv = self._inventory_repo.get_by_id(aisle.inventory_id)
        if (
            inv is not None
            and inv.processing_mode == InventoryProcessingMode.PRODUCTION
            and self._operational_promotion_service is not None
        ):
            promotion = self._operational_promotion_service.promote_for_success(
                aisle_id=aisle.id,
                candidate_job_id=job_id,
            )
            refreshed = self._aisle_repo.get_by_id(aisle.id)
            if refreshed is not None:
                aisle.operational_job_id = refreshed.operational_job_id
            logger.info(
                "v3_mark_success promotion outcome=%s job_id=%s operational=%s",
                promotion.outcome.value,
                job_id,
                aisle.operational_job_id,
            )
            return promotion.outcome.value
        if inv is not None and inv.processing_mode == InventoryProcessingMode.PRODUCTION:
            aisle.operational_job_id = job_id
        return PromotionOutcome.PROMOTED.value

    def fail_job(
        self,
        job_id: str,
        error_message: str,
        *,
        failure_code: str = "PROCESSING_FAILED",
    ) -> None:
        self.try_transition_to_failed(
            job_id, error_message, failure_code=failure_code
        )

    def try_transition_to_failed(
        self,
        job_id: str,
        error_message: str,
        *,
        failure_code: str = "PROCESSING_FAILED",
    ) -> bool:
        """CAS-style terminal fail: only active statuses may become FAILED.

        Returns True when this caller won the transition. Never reopens FAILED/CANCELED/
        SUCCEEDED into another terminal or RUNNING.
        """
        job = self._job_repo.get_by_id(job_id)
        if job is None:
            return False
        if job.status not in (
            JobStatus.STARTING,
            JobStatus.RUNNING,
            JobStatus.CANCEL_REQUESTED,
        ):
            logger.info(
                "job.terminal_transition_skipped job_id=%s current_status=%s "
                "wanted=FAILED failure_code=%s",
                job_id,
                job.status.value,
                failure_code,
            )
            return False
        now = self._clock.now()
        job.status = JobStatus.FAILED
        job.updated_at = now
        job.finished_at = now
        job.last_heartbeat_at = now
        job.failure_code = failure_code
        job.failure_message = (
            error_message[:2048] if len(error_message) > 2048 else error_message
        )
        job.error_message = job.failure_message
        self._job_repo.save(job)
        return True

    def try_transition_to_succeeded(self, job_id: str) -> Job | None:
        """Load job only if still eligible for success finalization (not already terminal)."""
        job = self._job_repo.get_by_id(job_id)
        if job is None:
            return None
        if job.status in (JobStatus.FAILED, JobStatus.CANCELED, JobStatus.SUCCEEDED):
            logger.info(
                "job.success_finalization_skipped job_id=%s current_status=%s",
                job_id,
                job.status.value,
            )
            return None
        if job.status not in (JobStatus.RUNNING, JobStatus.STARTING):
            return None
        return job

    def cancel_job(self, job: Job, reason: str, *, now, lease: JobLease | None = None) -> None:
        if lease is not None:
            write = self._job_repo.acknowledge_cancel_if_leased(
                lease, now=now, reason=reason
            )
            if write.outcome != LeaseWriteOutcome.APPLIED:
                raise JobLeaseLostError(
                    "Lease lost during cancel acknowledgement",
                    job_id=job.id,
                    owner_id=lease.owner_id,
                    fencing_token=lease.fencing_token,
                    reason=write.reason,
                )
            return
        # Legacy / external paths without a worker lease (e.g. pre-claim cancel).
        job.status = JobStatus.CANCELED
        job.updated_at = now
        job.finished_at = now
        job.last_heartbeat_at = now
        job.current_stage = job.current_stage or "Pipeline"
        job.current_substep = "canceled"
        job.failure_code = "CANCELED"
        job.failure_message = reason[:2048] if len(reason) > 2048 else reason
        job.error_message = reason[:2048] if len(reason) > 2048 else reason
        if job.finalization_status == FinalizationStatus.IN_PROGRESS:
            job.finalization_status = FinalizationStatus.CANCELED
            job.finalization_error_code = FinalizationErrorCode.FINALIZATION_CANCELED.value
        self._job_repo.save(job)

    def heartbeat(self, job_id: str) -> Job | None:
        """Unfenced heartbeat (legacy). Prefer :meth:`heartbeat_with_lease` for Phase 3 workers."""
        job = self._job_repo.get_by_id(job_id)
        if job is None or job.status not in (
            JobStatus.STARTING,
            JobStatus.RUNNING,
            JobStatus.CANCEL_REQUESTED,
        ):
            return None
        now = self._clock.now()
        job.last_heartbeat_at = now
        job.updated_at = now
        self._job_repo.save(job)
        return job

    def heartbeat_with_lease(
        self,
        lease: JobLease,
        *,
        extension_seconds: int,
    ) -> tuple[Job | None, LeaseRenewalResult]:
        """Renew lease + heartbeat. On LEASE_LOST do not mark the job failed."""
        now = self._clock.now()
        result = self._job_repo.touch_heartbeat_if_leased(
            lease, now=now, extension_seconds=extension_seconds
        )
        if result.outcome != LeaseRenewalOutcome.RENEWED:
            return None, result
        job = self._job_repo.get_by_id(lease.job_id)
        return job, result

    def update_runtime_status(self, job_id: str, *, stage: str, substep: str | None) -> None:
        job = self._job_repo.get_by_id(job_id)
        if job is None or job.status in (JobStatus.FAILED, JobStatus.CANCELED, JobStatus.SUCCEEDED):
            return
        now = self._clock.now()
        stage_changed = job.current_stage != stage
        substep_changed = job.current_substep != substep
        job.current_stage = stage
        job.current_substep = substep
        if stage_changed or substep_changed or job.current_step_started_at is None:
            job.current_step_started_at = now
        job.last_heartbeat_at = now
        job.updated_at = now
        self._job_repo.save(job)

    def fail_job_and_aisle(
        self,
        job_id: str,
        aisle: Aisle,
        error_message: str,
        *,
        failure_code: str = "PROCESSING_FAILED",
        lease: JobLease | None = None,
    ) -> bool:
        """Fail job+aisle if the job transition wins. Returns False if already terminal / lease lost."""
        now = self._clock.now()
        if lease is not None:
            write = self._job_repo.fail_if_leased(
                lease,
                now=now,
                error_message=error_message,
                failure_code=failure_code,
            )
            if write.outcome != LeaseWriteOutcome.APPLIED:
                logger.info(
                    "event=job_stale_write_rejected job_id=%s operation=fail_job_and_aisle "
                    "owner_id=%s fencing_token=%s outcome=%s reason=%s",
                    job_id,
                    lease.owner_id,
                    lease.fencing_token,
                    write.outcome.value,
                    write.reason,
                )
                return False
            won = True
        else:
            won = self.try_transition_to_failed(
                job_id, error_message, failure_code=failure_code
            )
        if not won:
            return False
        if self._operational_promotion_service is not None and (
            self._operational_promotion_service.is_stale_non_operational_failure(
                aisle_id=aisle.id,
                failing_job_id=job_id,
            )
        ):
            logger.warning(
                "v3_fail_job_and_aisle stale failure suppressed for aisle_id=%s job_id=%s "
                "operational_job_id=%s",
                aisle.id,
                job_id,
                aisle.operational_job_id,
            )
            self.reconcile_inventory_for_aisle(aisle)
            return True
        aisle_error = failure_code if failure_code != "PROCESSING_FAILED" else "PROCESSING_FAILED"
        self._fail_aisle_for_finalization(
            aisle,
            failing_job_id=job_id,
            error_code=aisle_error,
            message=error_message,
            now=now,
        )
        return True

    def merge_result_json_protected(
        self,
        job_id: str,
        patch: dict[str, Any],
        *,
        lease: JobLease | None,
    ) -> None:
        """Merge ``result_json`` under fencing CAS. Modern jobs must pass a non-None lease."""
        if lease is None:
            raise ValueError(
                f"merge_result_json_protected requires JobLease for modern jobs (job_id={job_id})"
            )
        write, _job = self._job_repo.merge_result_json_if_leased(
            lease, patch, now=self._clock.now()
        )
        if write.outcome != LeaseWriteOutcome.APPLIED:
            raise JobLeaseLostError(
                "Lease lost during result_json merge",
                job_id=job_id,
                owner_id=lease.owner_id,
                fencing_token=lease.fencing_token,
                reason=write.reason,
            )

    def _fail_aisle_for_finalization(
        self,
        aisle: Aisle,
        *,
        failing_job_id: str,
        error_code: str,
        message: str,
        now=None,
    ) -> None:
        ts = now if now is not None else self._clock.now()
        if self._operational_promotion_service is not None and (
            self._operational_promotion_service.is_stale_non_operational_failure(
                aisle_id=aisle.id,
                failing_job_id=failing_job_id,
            )
        ):
            self.reconcile_inventory_for_aisle(aisle)
            return
        aisle.mark_failed(
            ts,
            error_code=error_code,
            error_message=message[:2048] if len(message) > 2048 else message,
            retryable=True,
        )
        self._aisle_repo.save(aisle)
        self.reconcile_inventory_for_aisle(aisle)

    def cancel_job_and_aisle(
        self,
        job_id: str,
        aisle: Aisle,
        reason: str,
        *,
        exec_log: ExecutionLogWriter | None = None,
        cancel_event_emitted: dict[str, bool] | None = None,
        tracker: JobFinalizationTracker | None = None,
        lease: JobLease | None = None,
    ) -> None:
        now = self._clock.now()
        current_job = self._job_repo.get_by_id(job_id)
        active_lease = lease or (tracker.lease if tracker is not None else None)
        if exec_log is not None:
            should_emit_canceled = cancel_event_emitted is None or not cancel_event_emitted.get(
                "cancelled", False
            )
            if should_emit_canceled:
                exec_log.structured_event(
                    job_id=job_id,
                    inventory_id=aisle.inventory_id,
                    aisle_id=aisle.id,
                    attempt=current_job.attempt_count if current_job is not None else 1,
                    stage="Pipeline",
                    substep="canceled",
                    event="job.canceled",
                    details={"reason": reason[:500]},
                )
                if cancel_event_emitted is not None:
                    cancel_event_emitted["cancelled"] = True
        if tracker is not None:
            try:
                if tracker.last_completed == LastCompletedFinalizationStep.DOMAIN_RESULTS_PERSISTED:
                    tracker.cancel_after_domain_commit(reason=reason)
                else:
                    tracker.cancel_before_domain_commit(reason=reason)
            except JobLeaseLostError:
                logger.info(
                    "event=job_lease_lost job_id=%s operation=cancel_ack "
                    "owner_id=%s fencing_token=%s stage=cancel_job_and_aisle",
                    job_id,
                    tracker.lease.owner_id,
                    tracker.lease.fencing_token,
                )
                raise
            current_job = self._job_repo.get_by_id(job_id)
        elif current_job is not None:
            self.cancel_job(current_job, reason, now=now, lease=active_lease)
        aisle.mark_failed(
            now,
            error_code="CANCELED",
            error_message=reason[:2048] if len(reason) > 2048 else reason,
            retryable=True,
        )
        self._aisle_repo.save(aisle)
        self.reconcile_inventory_for_aisle(aisle)

    def cancel_finalization_after_domain_commit(
        self,
        job_id: str,
        aisle: Aisle,
        reason: str,
        *,
        tracker: JobFinalizationTracker,
        exec_log: ExecutionLogWriter | None = None,
        cancel_event_emitted: dict[str, bool] | None = None,
        lease: JobLease | None = None,
    ) -> None:
        """Post-commit cancellation: domain rows retained, job CANCELED, no artifacts."""
        self.cancel_job_and_aisle(
            job_id,
            aisle,
            reason,
            exec_log=exec_log,
            cancel_event_emitted=cancel_event_emitted,
            tracker=tracker,
            lease=lease or tracker.lease,
        )

    def raise_if_cancellation_requested(
        self,
        job_id: str,
        *,
        exec_log: ExecutionLogWriter,
        inventory_id: str,
        aisle_id: str,
        stage: str,
        substep: str | None,
        reason: str,
        cancel_event_emitted: dict[str, bool],
    ) -> None:
        current_job = self._job_repo.get_by_id(job_id)
        if current_job is None or current_job.status != JobStatus.CANCEL_REQUESTED:
            return
        if not cancel_event_emitted["requested"]:
            exec_log.structured_event(
                job_id=job_id,
                inventory_id=inventory_id,
                aisle_id=aisle_id,
                attempt=current_job.attempt_count,
                stage=stage,
                substep=substep,
                event="job.cancel_requested",
                details={"cancel_requested_at": current_job.cancel_requested_at},
            )
            cancel_event_emitted["requested"] = True
        if not cancel_event_emitted["detected"]:
            exec_log.structured_event(
                job_id=job_id,
                inventory_id=inventory_id,
                aisle_id=aisle_id,
                attempt=current_job.attempt_count,
                stage=stage,
                substep=substep,
                event="job.cancel_detected",
                details={
                    "cancel_requested_at": current_job.cancel_requested_at,
                    "reason": reason,
                },
            )
            cancel_event_emitted["detected"] = True
        raise PipelineCancellationRequestedError(reason)

    def fail_finalization_and_aisle(
        self,
        job_id: str,
        aisle: Aisle,
        *,
        tracker: JobFinalizationTracker,
        error_code: FinalizationErrorCode,
        current_step: CurrentFinalizationStep,
        message: str,
        metadata: dict[str, Any] | None = None,
        job_status: JobStatus = JobStatus.FAILED,
    ) -> None:
        try:
            report_finalization_failure(
                tracker,
                error_code=error_code,
                current_step=current_step,
                message=message,
                metadata=metadata,
                job_status=job_status,
            )
        except Exception as reporting_exc:
            logger.critical(
                "finalization_job_metadata_unavailable job_id=%s aisle_id=%s step=%s code=%s "
                "failure_state_persisted=false reporting_error_type=%s",
                job_id,
                aisle.id,
                current_step.value,
                error_code.value,
                type(reporting_exc).__name__,
                exc_info=reporting_exc,
            )
        self._fail_aisle_for_finalization(
            aisle,
            failing_job_id=job_id,
            error_code=error_code.value,
            message=message,
        )

    def mark_artifact_publication_retry_pending(
        self,
        job_id: str,
        *,
        tracker: JobFinalizationTracker,
        retry_kinds: set[str],
        published_kinds: set[str] | None = None,
    ) -> None:
        """Keep job active while autonomous outbox worker retries publication."""
        now = self._clock.now()
        tracker.set_current_step(CurrentFinalizationStep.PUBLISH_ARTIFACTS)
        job = self._job_repo.get_by_id(job_id)
        if job is None:
            return
        job.status = JobStatus.RUNNING
        job.finalization_status = FinalizationStatus.IN_PROGRESS
        job.current_finalization_step = CurrentFinalizationStep.PUBLISH_ARTIFACTS
        job.last_heartbeat_at = now
        job.updated_at = now
        self._job_repo.save(job)
        logger.info(
            "artifact.publication.retry_pending job_id=%s retry_kinds=%s published_kinds=%s",
            job_id,
            sorted(retry_kinds),
            sorted(published_kinds or []),
        )
