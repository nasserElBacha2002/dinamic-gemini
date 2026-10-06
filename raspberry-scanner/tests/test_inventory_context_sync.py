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


if __name__ == "__main__":
    unittest.main()
