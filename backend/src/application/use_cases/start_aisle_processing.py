"""
StartAisleProcessing use case — v3.0 (Épica 4).

Creates a processing job for an aisle and enqueues it. Fails if aisle does not exist,
aisle does not belong to the given inventory, or an active job already exists for the aisle.
"""

from __future__ import annotations

from dataclasses import dataclass
import uuid

from src.application.services.inventory_status_reconciler import InventoryStatusReconciler
from src.application.ports.repositories import AisleRepository, JobRepository
from src.application.ports.services import WorkerLaunchService
from src.application.ports.clock import Clock
from src.application.ports.contracts import ProcessAislePayload
from src.application.errors import AisleNotFoundError, ActiveJobExistsError
from src.domain.aisle.entities import Aisle
from src.domain.jobs.entities import Job, JobStatus
from src.config import load_settings


@dataclass
class StartAisleProcessingCommand:
    inventory_id: str
    aisle_id: str


class StartAisleProcessingUseCase:
    def __init__(
        self,
        aisle_repo: AisleRepository,
        job_repo: JobRepository,
        worker_launch_service: WorkerLaunchService,
        clock: Clock,
        status_reconciler: InventoryStatusReconciler,
    ) -> None:
        self._aisle_repo = aisle_repo
        self._job_repo = job_repo
        self._worker_launch_service = worker_launch_service
        self._clock = clock
        self._status_reconciler = status_reconciler

    def execute(self, command: StartAisleProcessingCommand) -> str:
        aisle = self._aisle_repo.get_by_id(command.aisle_id)
        if aisle is None:
            raise AisleNotFoundError(f"Aisle not found: {command.aisle_id}")
        if aisle.inventory_id != command.inventory_id:
            raise AisleNotFoundError(
                f"Aisle {command.aisle_id} does not belong to inventory {command.inventory_id}"
            )

        latest = self._job_repo.get_latest_by_target("aisle", command.aisle_id)
        if latest is not None and latest.status in (
            JobStatus.STARTING,
            JobStatus.RUNNING,
            JobStatus.CANCEL_REQUESTED,
        ):
            stale_after_seconds = int(getattr(load_settings(), "worker_stale_running_timeout_sec", 0) or 0)
            if stale_after_seconds > 0:
                now = self._clock.now()
                reference = latest.last_heartbeat_at or latest.updated_at
                if (now - reference).total_seconds() >= stale_after_seconds:
                    latest.status = JobStatus.FAILED
                    latest.failure_code = "STALE_JOB"
                    latest.failure_message = "Job heartbeat expired before completion"
                    latest.error_message = latest.failure_message
                    latest.finished_at = now
                    latest.updated_at = now
                    self._job_repo.save(latest)
        latest = self._job_repo.get_latest_by_target("aisle", command.aisle_id)
        if latest is not None and latest.status in (
            JobStatus.QUEUED,
            JobStatus.STARTING,
            JobStatus.RUNNING,
            JobStatus.CANCEL_REQUESTED,
        ):
            raise ActiveJobExistsError(
                f"Aisle {command.aisle_id} already has an active job (status={latest.status.value})"
            )

        now = self._clock.now()
        payload: ProcessAislePayload = {"aisle_id": command.aisle_id}
        # Concurrency safety: persist the job first, then enqueue its id.
        job_id = str(uuid.uuid4())
        job = Job(
            id=job_id,
            target_type="aisle",
            target_id=command.aisle_id,
            job_type="process_aisle",
            status=JobStatus.QUEUED,
            payload_json=dict(payload),
            created_at=now,
            updated_at=now,
            attempt_count=1,
            execution_id=job_id,
        )
        self._job_repo.save(job)

        aisle.mark_queued(now)
        self._aisle_repo.save(aisle)
        self._status_reconciler.reconcile(command.inventory_id)

        # On-demand worker launch: persist first, then spawn a single-job worker process.
        # If launch fails we must not leave an active queued/starting job behind.
        try:
            execution_id = self._worker_launch_service.launch(job_id)
            job.status = JobStatus.STARTING
            job.execution_id = execution_id
            job.started_at = now
            job.current_stage = "worker_launch"
            job.current_substep = "spawn_succeeded"
            job.current_step_started_at = now
            job.updated_at = now
            self._job_repo.save(job)
        except Exception as e:
            enqueue_error = f"Worker launch failed: {e}"

            job.status = JobStatus.FAILED
            job.error_message = enqueue_error
            job.failure_code = "WORKER_LAUNCH_FAILED"
            job.failure_message = enqueue_error
            job.finished_at = now
            job.updated_at = now
            self._job_repo.save(job)

            aisle.mark_failed(
                now,
                error_message=enqueue_error,
            )
            self._aisle_repo.save(aisle)
            self._status_reconciler.reconcile(command.inventory_id)
            raise

        return job_id
