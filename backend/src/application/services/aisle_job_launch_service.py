"""Launch process-aisle jobs for v3.

Phase 1 stores placeholder provider/prompt fields on ``Job`` for indexing and future tuning;
selection of multiple providers is out of scope until Phase 2+.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from src.application.ports.clock import Clock
from src.application.ports.contracts import ProcessAislePayload
from src.application.ports.repositories import AisleRepository, JobRepository
from src.application.ports.services import WorkerLaunchService
from src.application.services.inventory_status_reconciler import InventoryStatusReconciler
from src.domain.aisle.entities import Aisle
from src.domain.aisle_identification.modes import (
    CONFIGURATION_SNAPSHOT_VERSION,
    AisleIdentificationExecutionStrategy,
    AisleIdentificationMode,
    AisleIdentificationModeSource,
)
from src.domain.jobs.entities import Job, JobStatus
from src.llm.prompt_composer.hybrid_assembly import DEFAULT_HYBRID_PROMPT_PROFILE

logger = logging.getLogger(__name__)


@dataclass
class AisleJobLaunchService:
    aisle_repo: AisleRepository
    job_repo: JobRepository
    worker_launch_service: WorkerLaunchService
    clock: Clock
    status_reconciler: InventoryStatusReconciler

    def create_and_launch_attempt(
        self,
        *,
        aisle: Aisle,
        payload: ProcessAislePayload,
        attempt_count: int,
        retry_of_job_id: str | None = None,
        log_prefix: str = "job.start_requested",
        provider_name: str,
        model_name: str | None,
        prompt_key: str,
        identification_mode: AisleIdentificationMode = AisleIdentificationMode.LEGACY_LLM,
        identification_mode_source: AisleIdentificationModeSource = (
            AisleIdentificationModeSource.SYSTEM_DEFAULT
        ),
        configuration_snapshot_version: int = CONFIGURATION_SNAPSHOT_VERSION,
        execution_strategy: AisleIdentificationExecutionStrategy = (
            AisleIdentificationExecutionStrategy.LEGACY_LLM
        ),
    ) -> Job:
        now = self.clock.now()
        job = Job(
            id=str(uuid.uuid4()),
            target_type="aisle",
            target_id=aisle.id,
            job_type="process_aisle",
            status=JobStatus.STARTING,
            payload_json=dict(payload),
            created_at=now,
            updated_at=now,
            started_at=now,
            current_stage="worker_launch",
            current_substep="spawn_requested",
            current_step_started_at=now,
            attempt_count=int(attempt_count or 1),
            retry_of_job_id=retry_of_job_id,
            provider_name=(provider_name or "").strip().lower(),
            model_name=(
                str(model_name).strip()
                if model_name is not None and str(model_name).strip()
                else None
            ),
            prompt_key=prompt_key or DEFAULT_HYBRID_PROMPT_PROFILE,
            engine_params_json=None,
            identification_mode=identification_mode,
            identification_mode_source=identification_mode_source,
            configuration_snapshot_version=int(
                configuration_snapshot_version or CONFIGURATION_SNAPSHOT_VERSION
            ),
            execution_strategy=execution_strategy,
        )
        self.job_repo.save(job)

        aisle.mark_queued(now)
        self.aisle_repo.save(aisle)
        self.status_reconciler.reconcile(aisle.inventory_id)
        logger.info(
            "%s job_id=%s aisle_id=%s inventory_id=%s attempt_count=%s retry_of_job_id=%s "
            "provider_name=%s model_name=%s prompt_key=%s identification_mode=%s "
            "identification_mode_source=%s configuration_snapshot_version=%s "
            "actual_execution_strategy=%s",
            log_prefix,
            job.id,
            aisle.id,
            aisle.inventory_id,
            job.attempt_count,
            retry_of_job_id,
            job.provider_name,
            job.model_name,
            job.prompt_key,
            job.identification_mode.value,
            job.identification_mode_source.value,
            job.configuration_snapshot_version,
            job.execution_strategy.value,
        )

        try:
            execution_id = self.worker_launch_service.launch(job.id)
            job.execution_id = execution_id
            job.current_substep = "spawn_succeeded"
            job.current_step_started_at = now
            job.updated_at = now
            self.job_repo.save(job)
            logger.info(
                "%s job_id=%s execution_id=%s attempt_count=%s retry_of_job_id=%s",
                "job.retry_spawn_succeeded" if retry_of_job_id else "job.spawn_succeeded",
                job.id,
                execution_id,
                job.attempt_count,
                retry_of_job_id,
            )
            return job
        except Exception as exc:
            launch_error = f"Worker launch failed: {exc}"
            job.status = JobStatus.FAILED
            job.error_message = launch_error
            job.failure_code = "WORKER_LAUNCH_FAILED"
            job.failure_message = launch_error
            job.finished_at = now
            job.updated_at = now
            job.current_substep = "spawn_failed"
            self.job_repo.save(job)

            aisle.mark_failed(
                now,
                error_message=launch_error,
            )
            self.aisle_repo.save(aisle)
            self.status_reconciler.reconcile(aisle.inventory_id)
            logger.info(
                "%s job_id=%s attempt_count=%s retry_of_job_id=%s error=%s",
                "job.retry_spawn_failed" if retry_of_job_id else "job.spawn_failed",
                job.id,
                job.attempt_count,
                retry_of_job_id,
                launch_error,
            )
            raise
