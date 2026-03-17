"""In-memory NormalizedLabelRepository — v3.2.3."""

from __future__ import annotations

from typing import Dict, List, Sequence

from src.application.ports.repositories import NormalizedLabelRepository
from src.domain.labels.entities import NormalizedLabel


class MemoryNormalizedLabelRepository(NormalizedLabelRepository):
    def __init__(self) -> None:
        self._store: Dict[str, NormalizedLabel] = {}

    def save_many(self, labels: List[NormalizedLabel]) -> None:
        for lb in labels:
            self._store[lb.id] = lb

    def list_for_scope(self, inventory_id: str, aisle_id: str) -> Sequence[NormalizedLabel]:
        return [
            lb
            for lb in self._store.values()
            if lb.inventory_id == inventory_id and lb.aisle_id == aisle_id
        ]

    def replace_for_scope(self, inventory_id: str, aisle_id: str) -> None:
        to_remove = [
            lid
            for lid, lb in self._store.items()
            if lb.inventory_id == inventory_id and lb.aisle_id == aisle_id
        ]
        for lid in to_remove:
            del self._store[lid]
