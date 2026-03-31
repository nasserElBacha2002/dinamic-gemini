"""
GetAisleProcessingStatus use case — v3.0 (Épica 4).

Returns the aisle and its latest job (if any) for operational status display.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from src.application.ports.repositories import AisleRepository, JobRepository
from src.application.errors import AisleNotFoundError
from src.config import load_settings
from src.domain.aisle.entities import Aisle
from src.domain.jobs.entities import Job, JobStatus


@dataclass
class AisleProcessingStatusResult:
    """Result of GetAisleProcessingStatusUseCase."""
    aisle: Aisle
    latest_job: Optional[Job]


class GetAisleProcessingStatusUseCase:
    def __init__(
        self,
        aisle_repo: AisleRepository,
        job_repo: JobRepository,
    ) -> None:
        self._aisle_repo = aisle_repo
        self._job_repo = job_repo

    def execute(self, inventory_id: str, aisle_id: str) -> AisleProcessingStatusResult:
        aisle = self._aisle_repo.get_by_id(aisle_id)
        if aisle is None:
            raise AisleNotFoundError(f"Aisle not found: {aisle_id}")
        if aisle.inventory_id != inventory_id:
            raise AisleNotFoundError(
                f"Aisle {aisle_id} does not belong to inventory {inventory_id}"
            )

        latest_job = self._job_repo.get_latest_by_target("aisle", aisle_id)
        if latest_job is not None and latest_job.status in (
            JobStatus.STARTING,
            JobStatus.RUNNING,
            JobStatus.CANCEL_REQUESTED,
        ):
            stale_after_seconds = int(getattr(load_settings(), "worker_stale_running_timeout_sec", 0) or 0)
            if stale_after_seconds > 0:
                reference = latest_job.last_heartbeat_at or latest_job.updated_at
                if (datetime.now(timezone.utc) - reference).total_seconds() >= stale_after_seconds:
                    latest_job.status = JobStatus.FAILED
                    latest_job.failure_code = "STALE_JOB"
                    latest_job.failure_message = "Job heartbeat expired before completion"
                    latest_job.error_message = latest_job.failure_message
                    latest_job.finished_at = datetime.now(timezone.utc)
                    latest_job.updated_at = latest_job.finished_at
                    self._job_repo.save(latest_job)
        return AisleProcessingStatusResult(aisle=aisle, latest_job=latest_job)
