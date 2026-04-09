"""Inventory processing mode helpers (production vs test-only features)."""

from __future__ import annotations

from src.application.errors import BenchmarkRequiresTestInventoryError
from src.domain.inventory.entities import Inventory, InventoryProcessingMode

TEST_ONLY_INVENTORY_FEATURE_MESSAGE = "This feature is only available for test inventories."


def require_test_inventory_for_experimental_features(inventory: Inventory) -> None:
    """Reject benchmark/compare/promote-style flows unless the inventory is in test mode."""
    if inventory.processing_mode != InventoryProcessingMode.TEST:
        raise BenchmarkRequiresTestInventoryError(TEST_ONLY_INVENTORY_FEATURE_MESSAGE)
