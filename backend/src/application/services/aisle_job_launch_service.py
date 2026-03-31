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
from src.domain.jobs.entities import Job, JobStatus

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
        )
        self.job_repo.save(job)

        aisle.mark_queued(now)
        self.aisle_repo.save(aisle)
        self.status_reconciler.reconcile(aisle.inventory_id)
        logger.info(
            "%s job_id=%s aisle_id=%s inventory_id=%s attempt_count=%s retry_of_job_id=%s",
            log_prefix,
            job.id,
            aisle.id,
            aisle.inventory_id,
            job.attempt_count,
            retry_of_job_id,
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
