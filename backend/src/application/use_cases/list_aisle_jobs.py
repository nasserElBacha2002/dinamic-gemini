"""List inventory jobs for one aisle (run browser / Phase 2)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from src.application.errors import InventoryNotFoundError
from src.application.ports.repositories import AisleRepository, InventoryRepository, JobRepository
from src.application.services.aisle_inventory_scope import require_aisle_scoped_to_inventory
from src.domain.jobs.entities import Job


@dataclass(frozen=True)
class ListAisleJobsCommand:
    inventory_id: str
    aisle_id: str
    limit: int = 50


@dataclass(frozen=True)
class ListAisleJobsResult:
    jobs: Sequence[Job]
    operational_job_id: str | None


class ListAisleJobsUseCase:
    def __init__(
        self,
        inventory_repo: InventoryRepository,
        aisle_repo: AisleRepository,
        job_repo: JobRepository,
    ) -> None:
        self._inventory_repo = inventory_repo
        self._aisle_repo = aisle_repo
        self._job_repo = job_repo

    def execute(self, command: ListAisleJobsCommand) -> ListAisleJobsResult:
        inv = self._inventory_repo.get_by_id(command.inventory_id)
        if inv is None:
            raise InventoryNotFoundError(f"Inventory not found: {command.inventory_id}")
        aisle = require_aisle_scoped_to_inventory(
            self._aisle_repo,
            inventory_id=command.inventory_id,
            aisle_id=command.aisle_id,
            detail_style="merged",
        )
        jobs = self._job_repo.list_jobs_for_target("aisle", command.aisle_id, limit=command.limit)
        return ListAisleJobsResult(
            jobs=jobs,
            operational_job_id=aisle.operational_job_id,
        )
