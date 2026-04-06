"""
StartAisleProcessing use case — v3.0 (Épica 4).

Creates a processing job for an aisle and enqueues it. Fails if aisle does not exist,
aisle does not belong to the given inventory, or an active job already exists for the aisle.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.application.services.aisle_job_launch_service import AisleJobLaunchService
from src.application.services.job_stale_reconciler import JobStaleReconciler
from src.application.ports.repositories import AisleRepository, JobRepository
from src.application.ports.contracts import ProcessAislePayload
from src.application.errors import AisleNotFoundError, ActiveJobExistsError
from src.domain.jobs.entities import Job, JobStatus


@dataclass
class StartAisleProcessingCommand:
    inventory_id: str
    aisle_id: str
    pipeline_provider_key: str = "gemini"
    prompt_key: str = "default"


class StartAisleProcessingUseCase:
    def __init__(
        self,
        aisle_repo: AisleRepository,
        job_repo: JobRepository,
        launch_service: AisleJobLaunchService,
        stale_reconciler: JobStaleReconciler,
    ) -> None:
        self._aisle_repo = aisle_repo
        self._job_repo = job_repo
        self._launch_service = launch_service
        self._stale_reconciler = stale_reconciler

    def execute(self, command: StartAisleProcessingCommand) -> str:
        aisle = self._aisle_repo.get_by_id(command.aisle_id)
        if aisle is None:
            raise AisleNotFoundError(f"Aisle not found: {command.aisle_id}")
        if aisle.inventory_id != command.inventory_id:
            raise AisleNotFoundError(
                f"Aisle {command.aisle_id} does not belong to inventory {command.inventory_id}"
            )

        latest = self._stale_reconciler.reconcile(
            self._job_repo.get_latest_by_target("aisle", command.aisle_id)
        )
        if latest is not None and latest.status in (
            JobStatus.QUEUED,
            JobStatus.STARTING,
            JobStatus.RUNNING,
            JobStatus.CANCEL_REQUESTED,
        ):
            raise ActiveJobExistsError(
                f"Aisle {command.aisle_id} already has an active job (status={latest.status.value})"
            )

        payload: ProcessAislePayload = {"aisle_id": command.aisle_id}
        job = self._launch_service.create_and_launch_attempt(
            aisle=aisle,
            payload=payload,
            attempt_count=1,
            retry_of_job_id=None,
            log_prefix="job.start_requested",
            provider_name=command.pipeline_provider_key,
            prompt_key=command.prompt_key,
        )
        return job.id
