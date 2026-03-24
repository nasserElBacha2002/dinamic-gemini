"""
List inventories with per-row aggregates for table/list screens (Sprint 1.2).

pending_review_count: positions with needs_review True under this inventory's aisles.
last_activity_at: max of inventory updated_at, aisle updated_at, position updated_at (UTC-aware).
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Sequence

from src.application.ports.contracts import InventoryListItem
from src.application.ports.repositories import AisleRepository, InventoryRepository, PositionRepository


def _max_dt(*values: datetime) -> datetime:
    return max(values)


class ListInventoryListItemsUseCase:
    def __init__(
        self,
        inventory_repo: InventoryRepository,
        aisle_repo: AisleRepository,
        position_repo: PositionRepository,
    ) -> None:
        self._inventory_repo = inventory_repo
        self._aisle_repo = aisle_repo
        self._position_repo = position_repo

    def execute(self) -> Sequence[InventoryListItem]:
        inventories = self._inventory_repo.list_all()
        out: List[InventoryListItem] = []
        for inv in inventories:
            aisles = self._aisle_repo.list_by_inventory(inv.id)
            aisle_ids = [a.id for a in aisles]
            positions = self._position_repo.list_by_aisles(aisle_ids) if aisle_ids else []
            pending = sum(1 for p in positions if p.needs_review)
            times: List[datetime] = [inv.updated_at, inv.created_at]
            for a in aisles:
                times.append(a.updated_at)
            for p in positions:
                times.append(p.updated_at)
            last_activity = _max_dt(*times) if times else inv.updated_at
            out.append(
                InventoryListItem(
                    inventory=inv,
                    aisles_count=len(aisles),
                    pending_review_count=pending,
                    last_activity_at=last_activity,
                )
            )
        return out
