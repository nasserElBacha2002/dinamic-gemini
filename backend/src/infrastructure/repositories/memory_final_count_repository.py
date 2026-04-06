"""In-memory FinalCountRepository — v3.2.3."""

from __future__ import annotations

from typing import Dict, List, Sequence

from src.application.ports.repositories import FinalCountRepository, LabelJobScope
from src.domain.labels.entities import FinalCountRecord


def _matches_label_job(job_id: LabelJobScope, row_job: str | None) -> bool:
    if job_id == "all":
        return True
    if job_id is None:
        return row_job is None
    return row_job == job_id


class MemoryFinalCountRepository(FinalCountRepository):
    def __init__(self) -> None:
        self._store: Dict[str, FinalCountRecord] = {}

    def save_many(self, records: List[FinalCountRecord]) -> None:
        for r in records:
            self._store[r.id] = r

    def list_for_scope(
        self,
        inventory_id: str,
        aisle_id: str,
        *,
        job_id: LabelJobScope = "all",
    ) -> Sequence[FinalCountRecord]:
        return [
            r
            for r in self._store.values()
            if r.inventory_id == inventory_id
            and r.aisle_id == aisle_id
            and _matches_label_job(job_id, r.job_id)
        ]

    def list_by_position(self, position_id: str) -> Sequence[FinalCountRecord]:
        return [r for r in self._store.values() if r.position_id == position_id]

    def replace_for_scope(
        self,
        inventory_id: str,
        aisle_id: str,
        *,
        job_id: LabelJobScope = "all",
    ) -> None:
        to_remove = [
            rid
            for rid, r in self._store.items()
            if r.inventory_id == inventory_id
            and r.aisle_id == aisle_id
            and _matches_label_job(job_id, r.job_id)
        ]
        for rid in to_remove:
            del self._store[rid]
