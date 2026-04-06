from __future__ import annotations

from dataclasses import dataclass

from src.application.errors import AisleNotFoundError, InventoryNotFoundError
from src.application.ports.repositories import AisleRepository, InventoryRepository
from src.application.use_cases.recompute_consolidated_counts import (
    RecomputeConsolidatedCountsCommand,
    RecomputeConsolidatedCountsResult,
    RecomputeConsolidatedCountsUseCase,
)


@dataclass
class RunAisleMergeCommand:
    inventory_id: str
    aisle_id: str


class RunAisleMergeUseCase:
    """Execute merge/consolidation as an explicit manual post-process operation."""

    def __init__(
        self,
        inventory_repo: InventoryRepository,
        aisle_repo: AisleRepository,
        recompute_use_case: RecomputeConsolidatedCountsUseCase,
    ) -> None:
        self._inventory_repo = inventory_repo
        self._aisle_repo = aisle_repo
        self._recompute = recompute_use_case

    def execute(self, command: RunAisleMergeCommand) -> RecomputeConsolidatedCountsResult:
        inv = self._inventory_repo.get_by_id(command.inventory_id)
        if inv is None:
            raise InventoryNotFoundError(f"Inventory not found: {command.inventory_id}")
        aisle = self._aisle_repo.get_by_id(command.aisle_id)
        if aisle is None or aisle.inventory_id != command.inventory_id:
            raise AisleNotFoundError(
                f"Aisle {command.aisle_id} does not belong to inventory {command.inventory_id}"
            )
        # Manual merge must update the visible results surface after operator action.
        return self._recompute.execute(
            RecomputeConsolidatedCountsCommand(
                inventory_id=command.inventory_id,
                aisle_id=command.aisle_id,
                apply_to_product_records=True,
                job_scope="all",
            )
        )

