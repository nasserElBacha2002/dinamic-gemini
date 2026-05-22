"""
Resolve a ``Job`` row in the context of an inventory-scoped aisle (read-only API paths).

Used by GET ``.../jobs/{job_id}``, execution-log, execution-log.txt, and hybrid-report routes
so validation stays in the application layer (Phase 6).
"""

from __future__ import annotations

from src.application.errors import JobDoesNotBelongToAisleError, JobNotFoundError
from src.application.ports.repositories import AisleRepository, JobRepository
from src.application.services.aisle_inventory_scope import require_aisle_scoped_to_inventory
from src.domain.jobs.entities import Job


class ResolveAisleJobForInventoryReadUseCase:
    def __init__(self, job_repo: JobRepository, aisle_repo: AisleRepository) -> None:
        self._job_repo = job_repo
        self._aisle_repo = aisle_repo

    def execute(self, inventory_id: str, aisle_id: str, job_id: str) -> Job:
        job = self._job_repo.get_by_id(job_id)
        if job is None:
            raise JobNotFoundError(f"Job not found: {job_id}")
        if job.target_type != "aisle" or job.target_id != aisle_id:
            raise JobDoesNotBelongToAisleError(f"Job {job_id} is not scoped to aisle {aisle_id}")
        require_aisle_scoped_to_inventory(
            self._aisle_repo,
            inventory_id=inventory_id,
            aisle_id=aisle_id,
            detail_style="strict",
        )
        return job
