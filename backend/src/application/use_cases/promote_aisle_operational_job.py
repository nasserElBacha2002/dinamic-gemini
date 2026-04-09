"""Phase 6 — promote a succeeded benchmark run to the aisle operational pointer."""

from __future__ import annotations

from dataclasses import dataclass

from src.application.errors import (
    AisleNotFoundError,
    InventoryNotFoundError,
    JobDoesNotBelongToAisleError,
    JobNotFoundError,
    JobPromotionNotAllowedError,
)
from src.application.services.inventory_processing_mode import (
    require_test_inventory_for_experimental_features,
)
from src.application.ports.repositories import AisleRepository, InventoryRepository, JobRepository
from src.domain.jobs.entities import JobStatus


@dataclass(frozen=True)
class PromoteAisleOperationalJobCommand:
    inventory_id: str
    aisle_id: str
    job_id: str


class PromoteAisleOperationalJobUseCase:
    def __init__(
        self,
        inventory_repo: InventoryRepository,
        aisle_repo: AisleRepository,
        job_repo: JobRepository,
    ) -> None:
        self._inventory_repo = inventory_repo
        self._aisle_repo = aisle_repo
        self._job_repo = job_repo

    def execute(self, command: PromoteAisleOperationalJobCommand) -> str:
        inv = self._inventory_repo.get_by_id(command.inventory_id)
        if inv is None:
            raise InventoryNotFoundError(f"Inventory not found: {command.inventory_id}")
        require_test_inventory_for_experimental_features(inv)
        aisle = self._aisle_repo.get_by_id(command.aisle_id)
        if aisle is None or aisle.inventory_id != command.inventory_id:
            raise AisleNotFoundError(
                f"Aisle {command.aisle_id} does not belong to inventory {command.inventory_id}"
            )

        job = self._job_repo.get_by_id(command.job_id)
        if job is None:
            raise JobNotFoundError(f"Job not found: {command.job_id}")
        if job.target_type != "aisle" or job.target_id != command.aisle_id:
            raise JobDoesNotBelongToAisleError(
                f"Job {command.job_id} is not scoped to aisle {command.aisle_id}"
            )
        if job.job_type != "process_aisle":
            raise JobPromotionNotAllowedError(
                f"Only process_aisle jobs can be promoted (got {job.job_type})"
            )
        if job.status != JobStatus.SUCCEEDED:
            raise JobPromotionNotAllowedError(
                f"Only succeeded jobs can be promoted (status={job.status.value})"
            )

        aisle.operational_job_id = command.job_id
        self._aisle_repo.save(aisle)
        return command.job_id
