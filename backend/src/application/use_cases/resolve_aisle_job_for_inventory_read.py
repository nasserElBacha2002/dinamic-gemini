"""
Resolve a ``Job`` row in the context of an inventory-scoped aisle (read-only API paths).

Used by GET ``.../jobs/{job_id}``, execution-log, execution-log.txt, and hybrid-report routes
so validation stays in the application layer (Phase 6).
"""

from __future__ import annotations

from typing import Tuple

from src.application.errors import (
    AisleNotFoundError,
    JobDoesNotBelongToAisleError,
    JobNotFoundError,
)
from src.application.ports.repositories import AisleRepository, JobRepository
from src.domain.aisle.entities import Aisle
from src.domain.jobs.entities import Job


class ResolveAisleJobForInventoryReadUseCase:
    def __init__(self, job_repo: JobRepository, aisle_repo: AisleRepository) -> None:
        self._job_repo = job_repo
        self._aisle_repo = aisle_repo

    def execute(self, inventory_id: str, aisle_id: str, job_id: str) -> Tuple[Job, Aisle]:
        job = self._job_repo.get_by_id(job_id)
        if job is None:
            raise JobNotFoundError(f"Job not found: {job_id}")
        if job.target_type != "aisle" or job.target_id != aisle_id:
            raise JobDoesNotBelongToAisleError(
                f"Job {job_id} is not scoped to aisle {aisle_id}"
            )
        aisle = self._aisle_repo.get_by_id(aisle_id)
        if aisle is None:
            raise AisleNotFoundError(f"Aisle not found: {aisle_id}")
        if aisle.inventory_id != inventory_id:
            raise AisleNotFoundError(
                f"Aisle {aisle_id} does not belong to inventory {inventory_id}"
            )
        return job, aisle
