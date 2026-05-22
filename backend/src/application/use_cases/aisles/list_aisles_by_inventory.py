"""
ListAislesByInventory use case — v3.0 (Épica 3).

Returns all aisles for a given inventory. Validates that the inventory exists;
raises InventoryNotFoundError if not. Order is implementation-defined (SQL: created_at DESC).
"""

from __future__ import annotations

from collections.abc import Sequence

from src.application.errors import InventoryNotFoundError
from src.application.ports.repositories import AisleRepository, InventoryRepository
from src.domain.aisle.entities import Aisle


class ListAislesByInventoryUseCase:
    def __init__(
        self,
        inventory_repo: InventoryRepository,
        aisle_repo: AisleRepository,
    ) -> None:
        self._inventory_repo = inventory_repo
        self._aisle_repo = aisle_repo

    def execute(self, inventory_id: str) -> Sequence[Aisle]:
        if self._inventory_repo.get_by_id(inventory_id) is None:
            raise InventoryNotFoundError(f"Inventory not found: {inventory_id}")
        return self._aisle_repo.list_by_inventory(inventory_id)
