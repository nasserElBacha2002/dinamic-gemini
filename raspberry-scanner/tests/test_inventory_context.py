import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.inventory_context_repository import InventoryContextRepository
from inventory_context import (
    InventoryContextError,
    InventoryOperationalConfig,
    inventory_context_path,
    load_inventory_operational_config,
    resolve_inventory_aisle_for_capture,
    sync_inventory_context_from_backend,
)
from recognition_config_bundle_fixture import sample_recognition_config_bundle


class InventoryContextPathTests(unittest.TestCase):
    def test_default_path_under_export_storage_without_explicit_env(self) -> None:
        root = Path(tempfile.mkdtemp())
        os.environ["DINAMIC_EXPORT_DIRECTORY"] = str(root / "exports")
        os.environ.pop("DINAMIC_INVENTORY_CONTEXT_PATH", None)
        self.assertEqual(inventory_context_path(), root / "inventory-context.json")


class InventoryContextRepositoryTests(unittest.TestCase):
    def test_oserror_maps_to_unreadable(self) -> None:
        root = Path(tempfile.mkdtemp())
        path = root / "inventory-context.json"
        path.write_text("{}", encoding="utf-8")
        path.chmod(0)
        repo = InventoryContextRepository(path)
        with self.assertRaises(InventoryContextError) as ctx:
            repo.load()
        self.assertEqual(ctx.exception.code, "INVENTORY_CONTEXT_UNREADABLE")
        path.chmod(0o600)


class InventoryContextAutoSyncTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp())
        os.environ["DINAMIC_EXPORT_DIRECTORY"] = str(self.root / "exports")
        os.environ.pop("DINAMIC_INVENTORY_CONTEXT_PATH", None)
        os.environ["DINAMIC_INVENTORY_ID"] = "inv-uuid-1"
        os.environ["DINAMIC_BACKEND_URL"] = "https://inventory.example.com"
        os.environ["DINAMIC_BACKEND_BEARER_TOKEN"] = "token"

    def tearDown(self) -> None:
        for key in (
            "DINAMIC_EXPORT_DIRECTORY",
            "DINAMIC_INVENTORY_ID",
            "DINAMIC_BACKEND_URL",
            "DINAMIC_BACKEND_BEARER_TOKEN",
        ):
            os.environ.pop(key, None)

    def test_load_triggers_sync_with_documented_env_only(self) -> None:
        bundle = sample_recognition_config_bundle()
        expected = InventoryOperationalConfig.from_dict(
            {
                "inventory_id": bundle["inventory_id"],
                "aisles": [
                    {"aisle_id": "aisle-uuid-a1", "aisle_code": "A1"},
                    {"aisle_id": "aisle-uuid-b2", "aisle_code": "B2"},
                ],
            }
        )

        seen: list[str] = []

        class FakeClient:
            def fetch_operational_config(self, inventory_id: str) -> InventoryOperationalConfig:
                seen.append(inventory_id)
                return expected

        with patch(
            "config.inventory_context_sync.InventoryContextBackendClient",
            return_value=FakeClient(),
        ):
            config = load_inventory_operational_config()
        self.assertEqual(seen, ["inv-uuid-1"])
        self.assertEqual(config.inventory_id, "inv-uuid-1")
        persisted = InventoryContextRepository(inventory_context_path()).load()
        assert persisted is not None
        self.assertEqual(persisted.inventory_id, "inv-uuid-1")

    def test_resolve_aisle_after_lazy_sync(self) -> None:
        bundle = sample_recognition_config_bundle()
        expected = InventoryOperationalConfig.from_dict(
            {
                "inventory_id": bundle["inventory_id"],
                "aisles": [{"aisle_id": "aisle-uuid-a1", "aisle_code": "A1"}],
            }
        )

        class FakeClient:
            def fetch_operational_config(self, _inventory_id: str) -> InventoryOperationalConfig:
                return expected

        with patch(
            "config.inventory_context_sync.InventoryContextBackendClient",
            return_value=FakeClient(),
        ):
            resolved = resolve_inventory_aisle_for_capture("A1")
        self.assertEqual(resolved.aisle_id, "aisle-uuid-a1")

    def test_sync_persists_to_default_path(self) -> None:
        expected = InventoryOperationalConfig.from_dict(
            {
                "inventory_id": "inv-uuid-1",
                "aisles": [{"aisle_id": "aisle-1", "aisle_code": "A1"}],
            }
        )

        class FakeClient:
            def fetch_operational_config(self, _inventory_id: str) -> InventoryOperationalConfig:
                return expected

        with patch(
            "config.inventory_context_sync.InventoryContextBackendClient",
            return_value=FakeClient(),
        ):
            sync_inventory_context_from_backend()
        path = inventory_context_path()
        self.assertTrue(path.is_file())
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["inventory_id"], "inv-uuid-1")


if __name__ == "__main__":
    unittest.main()
