"""
List inventories with per-row aggregates for the **screen-ready** inventories table (Sprint 1.2).

**Contract:** This use case backs ``GET /api/v3/inventories``, which returns
``InventoryListItemResponse`` — not the thin ``InventoryResponse`` shape used for GET-by-id
and create.

**Aggregates:**
- ``pending_review_count``: positions with ``needs_review`` true under this inventory's aisles.
- ``last_activity_at``: max of persisted ``updated_at`` / ``created_at`` on the inventory row,
  each related aisle, and each related position. It is a **freshness signal for list sorting
  and “recent activity” columns** — not a dedicated “last human review” or “last job completed”
  event (those may be added later if product requires).

**Performance:** Implementation walks each inventory and calls aisle + position repositories.
That is correct for small/medium data volumes and in-memory tests; for large SQL deployments,
a future optimization may replace this with fewer query-oriented reads (same DTO).
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
                times.append(a.created_at)
            for p in positions:
                times.append(p.updated_at)
                times.append(p.created_at)
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
