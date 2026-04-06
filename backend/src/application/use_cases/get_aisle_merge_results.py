from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from src.application.errors import AisleNotFoundError, InventoryNotFoundError
from src.application.ports.repositories import (
    AisleRepository,
    FinalCountRepository,
    InventoryRepository,
)
from src.domain.labels.entities import FinalCountRecord


@dataclass
class GetAisleMergeResultsCommand:
    inventory_id: str
    aisle_id: str


class GetAisleMergeResultsUseCase:
    """Returns final_count rows for an aisle (Phase 1: unfiltered = all job slices; run-specific UI is Phase 2)."""

    def __init__(
        self,
        inventory_repo: InventoryRepository,
        aisle_repo: AisleRepository,
        final_count_repo: FinalCountRepository,
    ) -> None:
        self._inventory_repo = inventory_repo
        self._aisle_repo = aisle_repo
        self._final_count_repo = final_count_repo

    def execute(self, command: GetAisleMergeResultsCommand) -> Sequence[FinalCountRecord]:
        inv = self._inventory_repo.get_by_id(command.inventory_id)
        if inv is None:
            raise InventoryNotFoundError(f"Inventory not found: {command.inventory_id}")
        aisle = self._aisle_repo.get_by_id(command.aisle_id)
        if aisle is None or aisle.inventory_id != command.inventory_id:
            raise AisleNotFoundError(
                f"Aisle {command.aisle_id} does not belong to inventory {command.inventory_id}"
            )
        return self._final_count_repo.list_for_scope(
            command.inventory_id, command.aisle_id, job_id="all"
        )

