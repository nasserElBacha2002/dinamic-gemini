"""
ListInventories use case — v3.0 (Backlog HU-2.2).

Returns all inventories from the repository. No filters in this slice.
"""

from __future__ import annotations

from typing import Sequence

from src.application.ports.repositories import InventoryRepository
from src.domain.inventory.entities import Inventory


class ListInventoriesUseCase:
    def __init__(self, inventory_repo: InventoryRepository) -> None:
        self._inventory_repo = inventory_repo

    def execute(self) -> Sequence[Inventory]:
        return self._inventory_repo.list_all()
