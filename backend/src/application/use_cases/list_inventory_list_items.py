"""
List inventories with per-row aggregates for the **screen-ready** inventories table (Sprint 1.2 + 1.4).

**Contract:** Backs ``GET /api/v3/inventories`` with optional search, status filter, sort, and pagination.

**Aggregates:** See Sprint 1.2 docstring (pending_review_count, last_activity_at, aisles_count).

**Performance:** Still computes aggregates per inventory row candidate (after name/status filters).
For aggregate-based sorts, all matching inventories are materialized then sorted in memory.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional, Sequence, Tuple

from src.application.ports.contracts import InventoryListItem, InventoryTableQuery
from src.application.ports.repositories import AisleRepository, InventoryRepository, PositionRepository
from src.domain.inventory.entities import Inventory


def _max_dt(*values: datetime) -> datetime:
    return max(values)


def _normalize_dir(sort_dir: str) -> bool:
    return (sort_dir or "desc").strip().lower() == "desc"


def _inventory_row_key(item: InventoryListItem, sort_by: str) -> tuple:
    sb = (sort_by or "created_at").strip().lower()
    inv = item.inventory
    if sb == "name":
        return (inv.name.lower(), inv.id)
    if sb == "updated_at":
        return (inv.updated_at, inv.id)
    if sb == "status":
        return (inv.status.value, inv.id)
    if sb == "last_activity_at":
        la = item.last_activity_at or inv.updated_at
        return (la, inv.id)
    if sb == "pending_review_count":
        return (item.pending_review_count, inv.id)
    if sb == "aisles_count":
        return (item.aisles_count, inv.id)
    # created_at default
    return (inv.created_at, inv.id)


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

    def _build_item(self, inv: Inventory) -> InventoryListItem:
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
        return InventoryListItem(
            inventory=inv,
            aisles_count=len(aisles),
            pending_review_count=pending,
            last_activity_at=last_activity,
        )

    def execute(self, query: Optional[InventoryTableQuery] = None) -> Tuple[Sequence[InventoryListItem], int]:
        q = query or InventoryTableQuery()
        invs = list(self._inventory_repo.list_all())
        search = (q.search or "").strip().lower() if q.search else None
        if search:
            invs = [i for i in invs if search in i.name.lower()]
        if q.status is not None and str(q.status).strip():
            st = str(q.status).strip()
            invs = [i for i in invs if i.status.value == st]

        rows = [self._build_item(inv) for inv in invs]
        reverse = _normalize_dir(q.sort_dir)
        rows.sort(key=lambda r: _inventory_row_key(r, q.sort_by), reverse=reverse)

        total = len(rows)
        page = max(1, q.page)
        page_size = max(1, min(q.page_size, 200))
        start = (page - 1) * page_size
        return rows[start : start + page_size], total
