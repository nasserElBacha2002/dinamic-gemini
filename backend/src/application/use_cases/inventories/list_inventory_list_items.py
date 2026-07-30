"""
List inventories with per-row aggregates for the **screen-ready** inventories table (Sprint 1.2 + 1.4).

**Contract:** Backs ``GET /api/v3/inventories`` with optional search, status filter, sort, and pagination.

**Client names:** Resolved in one batch (``ClientRepository.get_by_ids``) for the current page.

**Performance:**
- Entity sorts (``name``, ``created_at``, ``updated_at``, ``status``): filter → sort → paginate,
  then one ``list_by_inventories`` + one ``list_by_aisles`` for the page only.
- Aggregate sorts (``aisles_count``, ``pending_review_count``, ``last_activity_at``): one
  ``list_by_inventories`` for all filtered inventories + one ``list_by_aisles``, then sort/page.
- Client names always batch-resolved once for the returned page.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime

from src.application.ports.contracts import InventoryListItem, InventoryTableQuery
from src.application.ports.repositories import (
    AisleRepository,
    ClientRepository,
    InventoryRepository,
    PositionRepository,
)
from src.application.services.inventory_aggregation_scope import scope_from_aisles
from src.domain.aisle.entities import Aisle
from src.domain.inventory.entities import Inventory
from src.domain.positions.entities import Position

_ENTITY_SORTS = frozenset({"name", "created_at", "updated_at", "status"})
_AGGREGATE_SORTS = frozenset({"aisles_count", "pending_review_count", "last_activity_at"})


def _max_dt(*values: datetime) -> datetime:
    return max(values)


def _normalize_dir(sort_dir: str) -> bool:
    return (sort_dir or "desc").strip().lower() == "desc"


def _sort_by_key(sort_by: str) -> str:
    sb = (sort_by or "created_at").strip().lower()
    if sb in _ENTITY_SORTS or sb in _AGGREGATE_SORTS:
        return sb
    return "created_at"


def _inventory_entity_key(inv: Inventory, sort_by: str) -> tuple:
    sb = _sort_by_key(sort_by)
    if sb == "name":
        return (inv.name.lower(), inv.id)
    if sb == "updated_at":
        return (inv.updated_at, inv.id)
    if sb == "status":
        return (inv.status.value, inv.id)
    return (inv.created_at, inv.id)


def _inventory_row_key(item: InventoryListItem, sort_by: str) -> tuple:
    sb = _sort_by_key(sort_by)
    inv = item.inventory
    if sb in _ENTITY_SORTS:
        return _inventory_entity_key(inv, sb)
    if sb == "last_activity_at":
        la = item.last_activity_at or inv.updated_at
        return (la, inv.id)
    if sb == "pending_review_count":
        return (item.pending_review_count, inv.id)
    if sb == "aisles_count":
        return (item.aisles_count, inv.id)
    return (inv.created_at, inv.id)


def _build_item_from_loaded(
    inv: Inventory,
    aisles: Sequence[Aisle],
    positions_by_aisle: dict[str, list[Position]],
    *,
    client_name: str | None = None,
) -> InventoryListItem:
    scope = scope_from_aisles(aisles)
    active_ids = list(scope.active_aisle_ids)
    positions: list[Position] = []
    for aid in active_ids:
        positions.extend(positions_by_aisle.get(aid, []))
    pending = sum(1 for p in positions if p.needs_review)
    times: list[datetime] = [inv.updated_at, inv.created_at]
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
        client_name=client_name,
    )


class ListInventoryListItemsUseCase:
    def __init__(
        self,
        inventory_repo: InventoryRepository,
        aisle_repo: AisleRepository,
        position_repo: PositionRepository,
        client_repo: ClientRepository,
    ) -> None:
        self._inventory_repo = inventory_repo
        self._aisle_repo = aisle_repo
        self._position_repo = position_repo
        self._client_repo = client_repo

    def _load_aggregates(
        self, invs: Sequence[Inventory]
    ) -> tuple[dict[str, list[Aisle]], dict[str, list[Position]]]:
        if not invs:
            return {}, {}
        aisles = list(self._aisle_repo.list_by_inventories([i.id for i in invs]))
        by_inv: dict[str, list[Aisle]] = defaultdict(list)
        for a in aisles:
            by_inv[a.inventory_id].append(a)
        active_ids: list[str] = []
        for inv in invs:
            scope = scope_from_aisles(by_inv.get(inv.id, []))
            active_ids.extend(scope.active_aisle_ids)
        positions = (
            list(self._position_repo.list_by_aisles(active_ids)) if active_ids else []
        )
        by_aisle: dict[str, list[Position]] = defaultdict(list)
        for p in positions:
            by_aisle[p.aisle_id].append(p)
        return by_inv, by_aisle

    def _enrich_client_names(
        self, rows: Sequence[InventoryListItem]
    ) -> list[InventoryListItem]:
        if not rows:
            return []
        client_ids = [r.inventory.client_id for r in rows if r.inventory.client_id]
        by_id = self._client_repo.get_by_ids(client_ids) if client_ids else {}
        enriched: list[InventoryListItem] = []
        for row in rows:
            cid = row.inventory.client_id
            name = by_id[cid].name if cid and cid in by_id else None
            enriched.append(
                InventoryListItem(
                    inventory=row.inventory,
                    aisles_count=row.aisles_count,
                    pending_review_count=row.pending_review_count,
                    last_activity_at=row.last_activity_at,
                    client_name=name,
                )
            )
        return enriched

    def execute(
        self, query: InventoryTableQuery | None = None
    ) -> tuple[Sequence[InventoryListItem], int]:
        q = query or InventoryTableQuery()
        invs = list(self._inventory_repo.list_all())
        search = (q.search or "").strip().lower() if q.search else None
        if search:
            invs = [i for i in invs if search in i.name.lower()]
        if q.status is not None and str(q.status).strip():
            st = str(q.status).strip()
            invs = [i for i in invs if i.status.value == st]

        sort_by = _sort_by_key(q.sort_by)
        reverse = _normalize_dir(q.sort_dir)
        page = max(1, q.page)
        page_size = max(1, min(q.page_size, 200))
        total = len(invs)

        if sort_by in _ENTITY_SORTS:
            invs.sort(key=lambda i: _inventory_entity_key(i, sort_by), reverse=reverse)
            start = (page - 1) * page_size
            page_invs = invs[start : start + page_size]
            by_inv, by_aisle = self._load_aggregates(page_invs)
            rows = [
                _build_item_from_loaded(
                    inv, by_inv.get(inv.id, []), by_aisle
                )
                for inv in page_invs
            ]
            return self._enrich_client_names(rows), total

        by_inv, by_aisle = self._load_aggregates(invs)
        rows = [
            _build_item_from_loaded(inv, by_inv.get(inv.id, []), by_aisle)
            for inv in invs
        ]
        rows.sort(key=lambda r: _inventory_row_key(r, sort_by), reverse=reverse)
        start = (page - 1) * page_size
        return self._enrich_client_names(rows[start : start + page_size]), total
