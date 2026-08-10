"""Inventory-scoped claim of physical product label_ids (count-once)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class InventoryCountedProductLabel:
    id: str
    inventory_id: str
    label_id: str
    first_product_record_id: str
    first_source_asset_id: str
    first_job_id: str
    first_position_id: str
    created_at: datetime


class InventoryCountedProductLabelRepository(Protocol):
    def try_claim(self, row: InventoryCountedProductLabel) -> bool:
        """Insert claim. Return True if this call won the unique slot; False if already claimed."""
        ...

    def get(self, inventory_id: str, label_id: str) -> InventoryCountedProductLabel | None: ...
