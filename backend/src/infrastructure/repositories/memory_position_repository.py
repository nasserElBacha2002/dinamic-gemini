"""
In-memory implementation of PositionRepository — v3.0 Épica 6.
"""

from __future__ import annotations

from collections.abc import Sequence

from src.application.ports.contracts import POSITION_LIST_JOB_ID_UNSET, PositionListQuery
from src.application.ports.repositories import JOB_ID_FILTER_UNSET, PositionRepository
from src.domain.positions.entities import Position


class MemoryPositionRepository(PositionRepository):
    def __init__(self) -> None:
        self._store: dict[str, Position] = {}

    def save(self, position: Position) -> None:
        self._store[position.id] = position

    def get_by_id(self, position_id: str) -> Position | None:
        return self._store.get(position_id)

    def list_by_aisle(
        self,
        aisle_id: str,
        status: str | None = None,
        needs_review: bool | None = None,
        min_confidence: float | None = None,
        sku_filter: str | None = None,
        page: int = 1,
        page_size: int = 25,
        sort_by: str = "created_at",
        sort_dir: str = "asc",
        job_id: str | None | object = JOB_ID_FILTER_UNSET,
    ) -> Sequence[Position]:
        # sku_filter is not supported in-memory (no product_record data); all positions for aisle are returned.
        positions = [p for p in self._store.values() if p.aisle_id == aisle_id]
        if job_id is not JOB_ID_FILTER_UNSET:
            if job_id is None:
                positions = [p for p in positions if p.job_id is None]
            else:
                positions = [p for p in positions if p.job_id == job_id]
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
        self, aisle_id: str, query: PositionListQuery | None = None
    ) -> Sequence[Position]:
        q = query or PositionListQuery()
        repo_job_id: str | None | object = JOB_ID_FILTER_UNSET
        if q.job_id is not POSITION_LIST_JOB_ID_UNSET:
            repo_job_id = q.job_id
        return self.list_by_aisle(
            aisle_id,
            status=q.status,
            needs_review=q.needs_review,
            min_confidence=q.min_confidence,
            sku_filter=q.sku_filter,
            page=q.page,
            page_size=q.page_size,
            sort_by=q.sort_by,
            sort_dir=q.sort_dir,
            job_id=repo_job_id,
        )

    def list_by_aisles(self, aisle_ids: Sequence[str]) -> Sequence[Position]:
        aid_set = set(aisle_ids)
        return [p for p in self._store.values() if p.aisle_id in aid_set]
