"""In-memory RawLabelRepository — v3.2.3."""

from __future__ import annotations

from collections.abc import Sequence

from src.application.ports.repositories import LabelJobScope, RawLabelRepository
from src.domain.labels.entities import RawLabel


def _matches_label_job(job_id: LabelJobScope, row_job: str | None) -> bool:
    if job_id == "all":
        return True
    if job_id is None:
        return row_job is None
    return row_job == job_id


class MemoryRawLabelRepository(RawLabelRepository):
    def __init__(self) -> None:
        self._store: dict[str, RawLabel] = {}

    def save_many(self, labels: list[RawLabel]) -> None:
        for lb in labels:
            self._store[lb.id] = lb

    def list_for_scope(
        self,
        inventory_id: str,
        aisle_id: str,
        *,
        job_id: LabelJobScope = "all",
    ) -> Sequence[RawLabel]:
        return [
            lb
            for lb in self._store.values()
            if lb.inventory_id == inventory_id
            and lb.aisle_id == aisle_id
            and _matches_label_job(job_id, lb.job_id)
        ]
