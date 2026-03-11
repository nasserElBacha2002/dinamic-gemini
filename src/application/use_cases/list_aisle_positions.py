"""
ListAislePositions use case — v3.0 Épica 6.

Returns positions for an aisle with optional filters and pagination.
Fails if inventory or aisle does not exist or aisle does not belong to inventory.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from src.application.ports.contracts import PositionListQuery
from src.application.ports.repositories import AisleRepository, InventoryRepository, PositionRepository
from src.application.errors import AisleNotFoundError, InventoryNotFoundError
from src.domain.positions.entities import Position


@dataclass
class ListAislePositionsCommand:
    inventory_id: str
    aisle_id: str
    query: Optional[PositionListQuery] = None


class ListAislePositionsUseCase:
    def __init__(
        self,
        inventory_repo: InventoryRepository,
        aisle_repo: AisleRepository,
        position_repo: PositionRepository,
    ) -> None:
        self._inventory_repo = inventory_repo
        self._aisle_repo = aisle_repo
        self._position_repo = position_repo

    def execute(self, command: ListAislePositionsCommand) -> Sequence[Position]:
        inv = self._inventory_repo.get_by_id(command.inventory_id)
        if inv is None:
            raise InventoryNotFoundError(f"Inventory not found: {command.inventory_id}")
        aisle = self._aisle_repo.get_by_id(command.aisle_id)
        if aisle is None:
            raise AisleNotFoundError(f"Aisle not found: {command.aisle_id}")
        if aisle.inventory_id != command.inventory_id:
            raise AisleNotFoundError(
                f"Aisle {command.aisle_id} does not belong to inventory {command.inventory_id}"
            )
        q = command.query
        if q is not None:
            return self._position_repo.list_by_aisle_query(command.aisle_id, q)
        return self._position_repo.list_by_aisle(command.aisle_id)
