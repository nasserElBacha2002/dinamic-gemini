from __future__ import annotations

import logging
from dataclasses import dataclass

from src.application.errors import AisleNotFoundError, ActiveJobExistsError
from src.application.ports.repositories import AisleRepository, JobRepository
from src.application.services.aisle_job_launch_service import AisleJobLaunchService
from src.application.services.job_stale_reconciler import JobStaleReconciler
from src.domain.jobs.entities import Job, JobStatus

logger = logging.getLogger(__name__)

RETRYABLE_JOB_STATUSES = (JobStatus.FAILED, JobStatus.CANCELED)
NON_RETRYABLE_JOB_STATUSES = (
    JobStatus.QUEUED,
    JobStatus.STARTING,
    JobStatus.RUNNING,
    JobStatus.CANCEL_REQUESTED,
    JobStatus.SUCCEEDED,
)


@dataclass
class RetryAisleJobCommand:
    inventory_id: str
    aisle_id: str
    job_id: str


class RetryAisleJobUseCase:
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

    def execute(self, command: RetryAisleJobCommand) -> Job:
        aisle = self._aisle_repo.get_by_id(command.aisle_id)
        if aisle is None or aisle.inventory_id != command.inventory_id:
            raise AisleNotFoundError(
                f"Aisle {command.aisle_id} does not belong to inventory {command.inventory_id}"
            )

        original_job = self._job_repo.get_by_id(command.job_id)
        if original_job is None:
            raise AisleNotFoundError(f"Job {command.job_id} not found for aisle {command.aisle_id}")
        if original_job.target_type != "aisle" or original_job.target_id != command.aisle_id:
            raise AisleNotFoundError(
                f"Job {command.job_id} does not belong to aisle {command.aisle_id}"
            )
        if original_job.job_type != "process_aisle":
            raise ValueError(f"Job {command.job_id} is not a process_aisle job")

        if original_job.status not in RETRYABLE_JOB_STATUSES:
            raise ValueError(
                f"Cannot retry job {command.job_id} with status {original_job.status.value!r}"
            )

        latest = self._stale_reconciler.reconcile(
            self._job_repo.get_latest_by_target("aisle", command.aisle_id)
        )
        if latest is not None and latest.status in NON_RETRYABLE_JOB_STATUSES:
            raise ActiveJobExistsError(
                f"Aisle {command.aisle_id} already has an active job (status={latest.status.value})"
            )

        payload = dict(original_job.payload_json or {})
        retry_job = self._launch_service.create_and_launch_attempt(
            aisle=aisle,
            payload=payload,
            attempt_count=int(original_job.attempt_count or 1) + 1,
            retry_of_job_id=original_job.id,
            log_prefix="job.retry_requested",
        )
        logger.info(
            "job.retry_requested previous_job_id=%s new_job_id=%s aisle_id=%s attempt_count=%s",
            original_job.id,
            retry_job.id,
            command.aisle_id,
            retry_job.attempt_count,
        )
        return retry_job
