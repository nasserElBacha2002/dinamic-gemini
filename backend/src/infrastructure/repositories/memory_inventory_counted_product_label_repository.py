"""In-memory inventory product-label claims (tests / local)."""

from __future__ import annotations

from src.application.ports.inventory_counted_product_label_repository import (
    InventoryCountedProductLabel,
    InventoryCountedProductLabelRepository,
)


class MemoryInventoryCountedProductLabelRepository(InventoryCountedProductLabelRepository):
    def __init__(self) -> None:
        self._by_key: dict[tuple[str, str], InventoryCountedProductLabel] = {}

    def try_claim(self, row: InventoryCountedProductLabel) -> bool:
        key = (row.inventory_id, row.label_id.upper())
        if key in self._by_key:
            return False
        self._by_key[key] = row
        return True

    def get(self, inventory_id: str, label_id: str) -> InventoryCountedProductLabel | None:
        return self._by_key.get((inventory_id, label_id.upper()))
