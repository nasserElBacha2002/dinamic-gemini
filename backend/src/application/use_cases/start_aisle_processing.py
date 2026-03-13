"""
StartAisleProcessing use case — v3.0 (Épica 4).

Creates a processing job for an aisle and enqueues it. Fails if aisle does not exist,
aisle does not belong to the given inventory, or an active job already exists for the aisle.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.application.ports.repositories import AisleRepository, JobRepository
from src.application.ports.services import JobQueue
from src.application.ports.clock import Clock
from src.application.ports.contracts import ProcessAislePayload
from src.application.errors import AisleNotFoundError, ActiveJobExistsError
from src.domain.aisle.entities import Aisle
from src.domain.jobs.entities import Job, JobStatus


@dataclass
class StartAisleProcessingCommand:
    inventory_id: str
    aisle_id: str


class StartAisleProcessingUseCase:
    def __init__(
        self,
        aisle_repo: AisleRepository,
        job_repo: JobRepository,
        job_queue: JobQueue,
        clock: Clock,
    ) -> None:
        self._aisle_repo = aisle_repo
        self._job_repo = job_repo
        self._job_queue = job_queue
        self._clock = clock

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
            JobStatus.QUEUED,
            JobStatus.RUNNING,
            JobStatus.CANCEL_REQUESTED,
        ):
            raise ActiveJobExistsError(
                f"Aisle {command.aisle_id} already has an active job (status={latest.status.value})"
            )

        payload: ProcessAislePayload = {"aisle_id": command.aisle_id}
        job_id = self._job_queue.enqueue("process_aisle", payload)

        now = self._clock.now()
        job = Job(
            id=job_id,
            target_type="aisle",
            target_id=command.aisle_id,
            job_type="process_aisle",
            status=JobStatus.QUEUED,
            payload_json=dict(payload),
            created_at=now,
            updated_at=now,
        )
        self._job_repo.save(job)

        aisle.mark_queued(now)
        self._aisle_repo.save(aisle)

        return job_id
