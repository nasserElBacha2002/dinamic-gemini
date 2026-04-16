"""
CancelAisleJob use case — v3.1.2 Stage 6.

Allows an operator to request cancellation of a v3 process_aisle job for an aisle.
Implements a simple state model:
    - QUEUED -> CANCELED (job never started)
    - RUNNING -> CANCEL_REQUESTED (cooperative cancellation; executor will mark CANCELED)
    - CANCEL_REQUESTED -> CANCEL_REQUESTED (idempotent)
Terminal states (SUCCEEDED, FAILED, CANCELED, TIMED_OUT) reject cancellation.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.application.ports.clock import Clock
from src.application.ports.repositories import AisleRepository, JobRepository
from src.application.services.aisle_inventory_scope import require_aisle_scoped_to_inventory
from src.application.services.process_aisle_job_for_aisle import (
    require_process_aisle_job_for_aisle,
)
from src.domain.jobs.entities import Job, JobStatus


@dataclass
class CancelAisleJobCommand:
    inventory_id: str
    aisle_id: str
    job_id: str


class CancelAisleJobUseCase:
    def __init__(
        self,
        aisle_repo: AisleRepository,
        job_repo: JobRepository,
        clock: Clock,
    ) -> None:
        self._aisle_repo = aisle_repo
        self._job_repo = job_repo
        self._clock = clock

    def execute(self, command: CancelAisleJobCommand) -> Job:
        """Request cancellation for a v3 process_aisle job.

        Behaviour:
        - If aisle or job do not exist or do not belong to the given inventory/aisle:
          raise AisleNotFoundError (mapped to 404 by the API).
        - If job is QUEUED: mark CANCELED immediately (never started).
        - If job is STARTING or RUNNING: mark CANCEL_REQUESTED (executor will cooperatively cancel).
        - If job is already CANCEL_REQUESTED: no-op (idempotent).
        - If job is terminal (SUCCEEDED / FAILED / CANCELED / TIMED_OUT): raise ValueError.
        """
        require_aisle_scoped_to_inventory(
            self._aisle_repo,
            inventory_id=command.inventory_id,
            aisle_id=command.aisle_id,
            detail_style="merged",
        )

        job = require_process_aisle_job_for_aisle(
            self._job_repo,
            job_id=command.job_id,
            aisle_id=command.aisle_id,
        )

        status = job.status
        if status in (
            JobStatus.SUCCEEDED,
            JobStatus.FAILED,
            JobStatus.CANCELED,
            JobStatus.TIMED_OUT,
        ):
            raise ValueError(
                f"Cannot cancel job {command.job_id} in terminal state {status.value!r}"
            )

        now = self._clock.now()
        if status == JobStatus.QUEUED:
            job.status = JobStatus.CANCELED
            job.updated_at = now
            job.cancel_requested_at = None
            job.finished_at = now
            if not job.error_message:
                job.error_message = "Job canceled before execution"
            self._job_repo.save(job)
            return job

        if status == JobStatus.CANCEL_REQUESTED:
            # Idempotent: already requested.
            return job

        # RUNNING (or any other non-terminal, non-queued state) → CANCEL_REQUESTED.
        job.status = JobStatus.CANCEL_REQUESTED
        job.updated_at = now
        job.cancel_requested_at = now
        if not job.error_message:
            job.error_message = "Job cancellation requested"
        self._job_repo.save(job)
        return job

