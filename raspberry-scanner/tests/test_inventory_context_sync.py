import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.inventory_context_sync import operational_config_from_recognition_bundle
from recognition_config_bundle_fixture import sample_recognition_config_bundle


class RecognitionConfigContractTests(unittest.TestCase):
    def test_operational_config_from_realistic_recognition_bundle(self) -> None:
        bundle = sample_recognition_config_bundle()
        config = operational_config_from_recognition_bundle(bundle)
        self.assertEqual(config.inventory_id, "inv-uuid-1")
        self.assertEqual(config.client_id, "client-uuid-1")
        codes = {code: aisle_id for code, aisle_id in config.aisles}
        self.assertEqual(codes["A1"], "aisle-uuid-a1")
        self.assertEqual(codes["B2"], "aisle-uuid-b2")
        self.assertNotIn(None, codes)
        self.assertEqual(len(config.aisles), 2)

    def test_missing_inventory_id_rejected(self) -> None:
        bundle = sample_recognition_config_bundle()
        bundle.pop("inventory_id")
        with self.assertRaises(Exception):
            operational_config_from_recognition_bundle(bundle)

    def test_list_inventories_filters_by_client_and_skips_invalid_rows(self) -> None:
        from config.inventory_context_sync import InventoryContextBackendClient

        pages = [
            {
                "items": [
                    {"id": "inv-a", "name": "A", "client_id": "client-a", "status": "draft"},
                    {"id": "inv-b", "name": "B", "client_id": "client-b", "status": "draft"},
                    {"name": "missing-id", "client_id": "client-a"},
                ],
                "total_pages": 1,
            }
        ]

        class FakeClient(InventoryContextBackendClient):
            def _get_json(self, url: str):
                return pages[0]

        entries = FakeClient("https://inventory.example.com", "token").list_inventories(
            client_id="client-a"
        )
        self.assertEqual([(row.inventory_id, row.client_id) for row in entries], [("inv-a", "client-a")])


if __name__ == "__main__":
    unittest.main()
