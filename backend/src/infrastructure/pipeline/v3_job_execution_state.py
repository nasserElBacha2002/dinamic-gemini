"""
Job and aisle lifecycle transitions for v3 ``process_aisle`` execution (Phase 2 split).

Extracted from :class:`~src.infrastructure.pipeline.v3_job_executor.V3JobExecutor` so the executor
coordinates without owning all persistence/state mutation details.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from src.application.ports.clock import Clock
from src.application.ports.repositories import AisleRepository, InventoryRepository, JobRepository
from src.application.services.inventory_status_reconciler import InventoryStatusReconciler
from src.domain.aisle.entities import Aisle
from src.domain.inventory.entities import InventoryProcessingMode
from src.domain.jobs.entities import Job, JobStatus
from src.infrastructure.pipeline.worker_durable_artifact_publisher import (
    merge_durable_into_result_json,
)
from src.pipeline.errors import PipelineCancellationRequestedError
from src.pipeline.execution_log import ExecutionLogWriter
from src.pipeline.run_metadata import (
    RUN_METADATA_KEY_LLM_COST_SNAPSHOT,
    RUN_METADATA_KEY_VISUAL_REFERENCE_CONTEXT,
    default_empty_block,
)

logger = logging.getLogger(__name__)


class V3JobExecutionStateService:
    """Mutates Job + Aisle domain state and inventory reconciliation for worker execution.

    Cooperative cancellation helpers (:meth:`raise_if_cancellation_requested`, :meth:`cancel_job_and_aisle`)
    intentionally emit structured events via :class:`~src.pipeline.execution_log.ExecutionLogWriter`
    before mutating persisted state. That couples lifecycle gates to execution observability in one
    callsite (historical worker behavior); splitting observability behind a dedicated port is deferred
    beyond Phase 2.
    """

    def __init__(
        self,
        *,
        job_repo: JobRepository,
        aisle_repo: AisleRepository,
        inventory_repo: InventoryRepository,
        clock: Clock,
        inventory_status_reconciler: InventoryStatusReconciler,
    ) -> None:
        self._job_repo = job_repo
        self._aisle_repo = aisle_repo
        self._inventory_repo = inventory_repo
        self._clock = clock
        self._inventory_status_reconciler = inventory_status_reconciler

    def reconcile_inventory_for_aisle(self, aisle: Aisle) -> None:
        self._inventory_status_reconciler.reconcile(aisle.inventory_id)

    def mark_running(self, job_id: str, aisle: Aisle, now) -> None:
        job = self._job_repo.get_by_id(job_id)
        if job:
            job.status = JobStatus.RUNNING
            job.started_at = job.started_at or now
            job.last_heartbeat_at = now
            job.current_stage = "Pipeline"
            job.current_substep = "startup_confirmed"
            job.current_step_started_at = now
            job.updated_at = now
            self._job_repo.save(job)
        aisle.mark_processing(now)
        self._aisle_repo.save(aisle)
        self.reconcile_inventory_for_aisle(aisle)

    def mark_success(
        self,
        job_id: str,
        aisle: Aisle,
        report_path: Path,
        *,
        run_metadata: dict | None = None,
        durable_artifacts: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        # Completion wall time at true terminal persist (after durable upload), not job start.
        completion_now = self._clock.now()
        job = self._job_repo.get_by_id(job_id)
        if job:
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
            if durable_artifacts:
                merge_durable_into_result_json(job.result_json, durable_artifacts)
                logger.info(
                    "v3_job_metadata_persist_durable_artifacts job_id=%s kinds=%s",
                    job_id,
                    sorted(durable_artifacts.keys()),
                )
            job.error_message = None
            job.failure_code = None
            job.failure_message = None
            self._job_repo.save(job)
            logger.info(
                "v3_job_metadata_save_ok job_id=%s has_durable_artifacts=%s",
                job_id,
                bool(durable_artifacts),
            )
        # Production: pin the aisle operational pointer to this succeeded job so default result reads
        # and review mutations use the same slice (ResultContextResolver + review_validation).
        # Policy: always set to job_id on success (latest succeeded run is operational). Test inventories
        # are unchanged here — operators use promote-operational for benchmark pinning.
        inv = self._inventory_repo.get_by_id(aisle.inventory_id)
        if inv is not None and inv.processing_mode == InventoryProcessingMode.PRODUCTION:
            aisle.operational_job_id = job_id
        aisle.mark_processed(completion_now)
        self._aisle_repo.save(aisle)
        self.reconcile_inventory_for_aisle(aisle)

    def fail_job(self, job_id: str, error_message: str) -> None:
        job = self._job_repo.get_by_id(job_id)
        if job:
            now = self._clock.now()
            job.status = JobStatus.FAILED
            job.updated_at = now
            job.finished_at = now
            job.last_heartbeat_at = now
            job.failure_code = "PROCESSING_FAILED"
            job.failure_message = (
                error_message[:2048] if len(error_message) > 2048 else error_message
            )
            job.error_message = error_message[:2048] if len(error_message) > 2048 else error_message
            self._job_repo.save(job)

    def cancel_job(self, job: Job, reason: str, *, now) -> None:
        job.status = JobStatus.CANCELED
        job.updated_at = now
        job.finished_at = now
        job.last_heartbeat_at = now
        job.current_stage = job.current_stage or "Pipeline"
        job.current_substep = "canceled"
        job.failure_code = "CANCELED"
        job.failure_message = reason[:2048] if len(reason) > 2048 else reason
        job.error_message = reason[:2048] if len(reason) > 2048 else reason
        self._job_repo.save(job)

    def heartbeat(self, job_id: str) -> Job | None:
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

    def fail_job_and_aisle(self, job_id: str, aisle: Aisle, error_message: str) -> None:
        now = self._clock.now()
        self.fail_job(job_id, error_message)
        aisle.mark_failed(
            now,
            error_code="PROCESSING_FAILED",
            error_message=error_message[:2048] if len(error_message) > 2048 else error_message,
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
    ) -> None:
        """Cancel the job and mark the aisle as failed-with-CANCELED, optionally logging ``job.canceled``.

        ``exec_log`` is optional so the same persistence path works without a writer; when present,
        ``job.canceled`` is emitted once per terminal cancel (mirrors pre–Phase 2 executor behavior).
        """
        now = self._clock.now()
        current_job = self._job_repo.get_by_id(job_id)
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
        if current_job is not None:
            self.cancel_job(current_job, reason, now=now)
        # The aisle lifecycle has no dedicated "canceled" state. We intentionally map
        # operator-driven cancellation to FAILED with error_code CANCELED so the aisle
        # remains visibly incomplete without introducing a parallel domain status.
        aisle.mark_failed(
            now,
            error_code="CANCELED",
            error_message=reason[:2048] if len(reason) > 2048 else reason,
            retryable=True,
        )
        self._aisle_repo.save(aisle)
        self.reconcile_inventory_for_aisle(aisle)

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
        """If the job is ``CANCEL_REQUESTED``, emit cancel events to ``exec_log`` then raise.

        Logging precedes :exc:`~src.pipeline.errors.PipelineCancellationRequestedError` so the
        worker trace shows ``cancel_requested`` / ``cancel_detected`` at the checkpoint that fired.
        """
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
