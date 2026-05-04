"""In-memory NormalizedLabelRepository — v3.2.3."""

from __future__ import annotations

from collections.abc import Sequence

from src.application.ports.repositories import LabelJobScope, NormalizedLabelRepository
from src.domain.labels.entities import NormalizedLabel


def _matches_label_job(job_id: LabelJobScope, row_job: str | None) -> bool:
    if job_id == "all":
        return True
    if job_id is None:
        return row_job is None
    return row_job == job_id


class MemoryNormalizedLabelRepository(NormalizedLabelRepository):
    def __init__(self) -> None:
        self._store: dict[str, NormalizedLabel] = {}

    def save_many(self, labels: list[NormalizedLabel]) -> None:
        for lb in labels:
            self._store[lb.id] = lb

    def list_for_scope(
        self,
        inventory_id: str,
        aisle_id: str,
        *,
        job_id: LabelJobScope = "all",
    ) -> Sequence[NormalizedLabel]:
        return [
            lb
            for lb in self._store.values()
            if lb.inventory_id == inventory_id
            and lb.aisle_id == aisle_id
            and _matches_label_job(job_id, lb.job_id)
        ]

    def replace_for_scope(
        self,
        inventory_id: str,
        aisle_id: str,
        *,
        job_id: LabelJobScope = "all",
    ) -> None:
        to_remove = [
            lid
            for lid, lb in self._store.items()
            if lb.inventory_id == inventory_id
            and lb.aisle_id == aisle_id
            and _matches_label_job(job_id, lb.job_id)
        ]
        for lid in to_remove:
            del self._store[lid]
