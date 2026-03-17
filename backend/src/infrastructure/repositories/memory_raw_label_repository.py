"""In-memory RawLabelRepository — v3.2.3."""

from __future__ import annotations

from typing import Dict, List, Sequence

from src.application.ports.repositories import RawLabelRepository
from src.domain.labels.entities import RawLabel


class MemoryRawLabelRepository(RawLabelRepository):
    def __init__(self) -> None:
        self._store: Dict[str, RawLabel] = {}

    def save_many(self, labels: List[RawLabel]) -> None:
        for lb in labels:
            self._store[lb.id] = lb

    def list_for_scope(self, inventory_id: str, aisle_id: str) -> Sequence[RawLabel]:
        return [
            lb
            for lb in self._store.values()
            if lb.inventory_id == inventory_id and lb.aisle_id == aisle_id
        ]
