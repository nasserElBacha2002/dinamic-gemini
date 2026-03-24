"""
Cross-inventory review queue — positions with ``needs_review`` (Sprint 1.4).

Uses existing repositories only (batch ``list_by_aisles``). Suitable for small/medium
deployments; very large multi-inventory installs may need a dedicated SQL path later.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from src.application.ports.contracts import ReviewQueueListRow, ReviewQueueQuery
from src.application.ports.repositories import AisleRepository, InventoryRepository, PositionRepository


def _sort_key(row: ReviewQueueListRow, sort_by: str) -> tuple:
    p = row.position
    sb = (sort_by or "updated_at").strip().lower()
    if sb == "created_at":
        return (p.created_at, p.id)
    if sb == "confidence":
        return (p.confidence, p.id)
    return (p.updated_at, p.id)


class ListReviewQueueUseCase:
    def __init__(
        self,
        inventory_repo: InventoryRepository,
        aisle_repo: AisleRepository,
        position_repo: PositionRepository,
    ) -> None:
        self._inventory_repo = inventory_repo
        self._aisle_repo = aisle_repo
        self._position_repo = position_repo

    def execute(self, query: Optional[ReviewQueueQuery] = None) -> Tuple[List[ReviewQueueListRow], int]:
        q = query or ReviewQueueQuery()
        scope: List[tuple] = []
        for inv in self._inventory_repo.list_all():
            if q.inventory_id is not None and str(q.inventory_id).strip() and inv.id != q.inventory_id:
                continue
            for aisle in self._aisle_repo.list_by_inventory(inv.id):
                if q.aisle_id is not None and str(q.aisle_id).strip() and aisle.id != q.aisle_id:
                    continue
                scope.append((inv, aisle))

        if not scope:
            return [], 0

        aisle_ids = [a.id for _, a in scope]
        by_aisle_id = {a.id: (inv, a) for inv, a in scope}
        positions = list(self._position_repo.list_by_aisles(aisle_ids))
        pending = [p for p in positions if p.needs_review]
        if q.min_confidence is not None:
            pending = [p for p in pending if p.confidence >= q.min_confidence]

        rows: List[ReviewQueueListRow] = []
        for p in pending:
            inv, aisle = by_aisle_id[p.aisle_id]
            rows.append(
                ReviewQueueListRow(
                    position=p,
                    inventory_id=inv.id,
                    inventory_name=inv.name,
                    aisle_code=aisle.code,
                )
            )

        reverse = (q.sort_dir or "desc").strip().lower() == "desc"
        rows.sort(key=lambda r: _sort_key(r, q.sort_by), reverse=reverse)
        total = len(rows)
        page = max(1, q.page)
        page_size = max(1, min(q.page_size, 200))
        start = (page - 1) * page_size
        return rows[start : start + page_size], total
