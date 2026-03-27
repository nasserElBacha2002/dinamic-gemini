"""
In-memory implementation of PositionRepository — v3.0 Épica 6.
"""

from __future__ import annotations

from typing import Dict, Optional, Sequence

from src.application.ports.contracts import PositionListQuery
from src.application.ports.repositories import PositionRepository
from src.domain.positions.entities import Position


class MemoryPositionRepository(PositionRepository):
    def __init__(self) -> None:
        self._store: Dict[str, Position] = {}

    def save(self, position: Position) -> None:
        self._store[position.id] = position

    def get_by_id(self, position_id: str) -> Optional[Position]:
        return self._store.get(position_id)

    def list_by_aisle(
        self,
        aisle_id: str,
        status: Optional[str] = None,
        needs_review: Optional[bool] = None,
        min_confidence: Optional[float] = None,
        sku_filter: Optional[str] = None,
        page: int = 1,
        page_size: int = 25,
        sort_by: str = "created_at",
        sort_dir: str = "asc",
    ) -> Sequence[Position]:
        # sku_filter is not supported in-memory (no product_record data); all positions for aisle are returned.
        positions = [p for p in self._store.values() if p.aisle_id == aisle_id]
        if status is not None:
            positions = [p for p in positions if (p.status.value == status)]
        if needs_review is not None:
            positions = [p for p in positions if p.needs_review == needs_review]
        if min_confidence is not None:
            positions = [p for p in positions if p.confidence >= min_confidence]
        sb = (sort_by or "created_at").strip().lower()
        reverse = (sort_dir or "asc").strip().lower() == "desc"

        def _key(p: Position) -> tuple:
            if sb == "updated_at":
                return (p.updated_at, p.id)
            if sb == "confidence":
                return (p.confidence, p.id)
            if sb == "id":
                return (p.id,)
            return (p.created_at, p.id)

        positions = sorted(positions, key=_key, reverse=reverse)
        start = (page - 1) * page_size
        return positions[start : start + page_size]

    def list_by_aisle_query(
        self, aisle_id: str, query: Optional[PositionListQuery] = None
    ) -> Sequence[Position]:
        q = query or PositionListQuery()
        return self.list_by_aisle(
            aisle_id,
            status=q.status,
            needs_review=q.needs_review,
            min_confidence=q.min_confidence,
            sku_filter=q.sku_filter,
            page=q.page,
            page_size=q.page_size,
        )

    def list_by_aisles(self, aisle_ids: Sequence[str]) -> Sequence[Position]:
        aid_set = set(aisle_ids)
        return [p for p in self._store.values() if p.aisle_id in aid_set]
