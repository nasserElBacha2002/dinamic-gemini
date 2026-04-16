"""
In-memory implementation of ProductRecordRepository — v3.0 Épica 6.
"""

from __future__ import annotations

from typing import Dict, Optional, Sequence

from src.application.ports.repositories import ProductRecordRepository
from src.domain.products.entities import ProductRecord


class MemoryProductRecordRepository(ProductRecordRepository):
    def __init__(self) -> None:
        self._store: Dict[str, ProductRecord] = {}

    def save(self, product: ProductRecord) -> None:
        self._store[product.id] = product

    def get_by_id(self, product_id: str) -> Optional[ProductRecord]:
        return self._store.get(product_id)

    def list_by_position(self, position_id: str) -> Sequence[ProductRecord]:
        return [
            p
            for p in self._store.values()
            if p.position_id == position_id
        ]

    def list_by_position_ids(self, position_ids: Sequence[str]) -> Sequence[ProductRecord]:
        wanted = frozenset(position_ids)
        if not wanted:
            return []
        return [p for p in self._store.values() if p.position_id in wanted]
