"""
ListAislesWithStatus use case — v3.0 (Épica 4 correction).

Returns aisles for an inventory with latest job per aisle in one batch.
Uses JobRepository.get_latest_by_targets to avoid N+1 in the API layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence

from src.application.ports.repositories import AisleRepository, InventoryRepository, JobRepository
from src.application.errors import InventoryNotFoundError
from src.domain.aisle.entities import Aisle
from src.domain.jobs.entities import Job


@dataclass
class AisleWithLatestJob:
    """Aisle plus its latest job if any."""
    aisle: Aisle
    latest_job: Optional[Job]


class ListAislesWithStatusUseCase:
    def __init__(
        self,
        inventory_repo: InventoryRepository,
        aisle_repo: AisleRepository,
        job_repo: JobRepository,
    ) -> None:
        self._inventory_repo = inventory_repo
        self._aisle_repo = aisle_repo
        self._job_repo = job_repo

    def execute(self, inventory_id: str) -> List[AisleWithLatestJob]:
        if self._inventory_repo.get_by_id(inventory_id) is None:
            raise InventoryNotFoundError(f"Inventory not found: {inventory_id}")
        aisles = self._aisle_repo.list_by_inventory(inventory_id)
        if not aisles:
            return []
        aisle_ids: Sequence[str] = [a.id for a in aisles]
        latest_by_aisle = self._job_repo.get_latest_by_targets("aisle", aisle_ids)
        return [
            AisleWithLatestJob(aisle=a, latest_job=latest_by_aisle.get(a.id))
            for a in aisles
        ]
