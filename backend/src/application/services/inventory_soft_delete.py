"""Soft-delete helpers for inventory operational paths."""

from __future__ import annotations

from src.application.errors import InventoryNotFoundError
from src.domain.inventory.entities import Inventory


def reject_if_inventory_deleted(inventory: Inventory) -> None:
    """Treat soft-deleted inventories as inaccessible for normal API/use cases."""
    if inventory.is_deleted:
        raise InventoryNotFoundError(f"Inventory not found: {inventory.id}")
