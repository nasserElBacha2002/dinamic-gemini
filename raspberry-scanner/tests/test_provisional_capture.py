"""Local aisle/inventory provisioning for capture."""

from __future__ import annotations

import unittest

from inventory_context import (
    InventoryOperationalConfig,
    resolve_or_provision_aisle_for_capture,
)
from provisional_ids import PENDING_AISLE_ID


class ProvisionalCaptureTests(unittest.TestCase):
    def test_unknown_aisle_uses_pending_id(self) -> None:
        config = InventoryOperationalConfig(
            inventory_id="inv-1",
            aisles=(("A1", "aisle-known"),),
            client_id="client-a",
        )
        resolved = resolve_or_provision_aisle_for_capture("NEW-PASILLO", config=config)
        self.assertEqual(resolved.aisle_id, PENDING_AISLE_ID)
        self.assertEqual(resolved.aisle_code, "NEW-PASILLO")

    def test_known_aisle_uses_catalog_id(self) -> None:
        config = InventoryOperationalConfig(
            inventory_id="inv-1",
            aisles=(("A1", "aisle-known"),),
            client_id="client-a",
        )
        resolved = resolve_or_provision_aisle_for_capture("A1", config=config)
        self.assertEqual(resolved.aisle_id, "aisle-known")