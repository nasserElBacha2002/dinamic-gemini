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


class InventoryOperationalConfigTests(unittest.TestCase):
    def test_from_dict_rejects_empty_aisles(self) -> None:
        with self.assertRaises(InventoryContextError) as ctx:
            InventoryOperationalConfig.from_dict(
                {
                    "inventory_id": "2986b4e0-db88-4d88-ad87-63246d23a4d1",
                    "client_id": "client-a",
                    "aisles": [],
                }
            )
        self.assertEqual(ctx.exception.code, "INVENTORY_CONTEXT_INVALID")
        self.assertIn("aisles must be a non-empty array", str(ctx.exception))


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
        os.environ["DINAMIC_DEVICE_TOKEN"] = "device-token"

    def tearDown(self) -> None:
        for key in (
            "DINAMIC_EXPORT_DIRECTORY",
            "DINAMIC_INVENTORY_ID",
            "DINAMIC_BACKEND_URL",
            "DINAMIC_DEVICE_TOKEN",
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
            def fetch_operational_config(self, inventory_id: str, **_kwargs) -> InventoryOperationalConfig:
                seen.append(inventory_id)
                return expected

        with patch(
            "config.inventory_context_sync.InventoryContextBackendClient",
            return_value=FakeClient(),
        ):
            config = load_inventory_operational_config(client_id="client-uuid-1")
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
            def fetch_operational_config(self, _inventory_id: str, **_kwargs) -> InventoryOperationalConfig:
                return expected

        with patch(
            "config.inventory_context_sync.InventoryContextBackendClient",
            return_value=FakeClient(),
        ):
            resolved = resolve_inventory_aisle_for_capture("A1", client_id="client-uuid-1")
        self.assertEqual(resolved.aisle_id, "aisle-uuid-a1")

    def test_sync_persists_to_default_path(self) -> None:
        expected = InventoryOperationalConfig.from_dict(
            {
                "inventory_id": "inv-uuid-1",
                "aisles": [{"aisle_id": "aisle-1", "aisle_code": "A1"}],
            }
        )

        class FakeClient:
            def fetch_operational_config(self, _inventory_id: str, **_kwargs) -> InventoryOperationalConfig:
                return expected

        with patch(
            "config.inventory_context_sync.InventoryContextBackendClient",
            return_value=FakeClient(),
        ):
            sync_inventory_context_from_backend(expected_client_id="client-uuid-1")
        path = inventory_context_path()
        self.assertTrue(path.is_file())
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["inventory_id"], "inv-uuid-1")


class InventoryContextDynamicTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp())
        os.environ["DINAMIC_EXPORT_DIRECTORY"] = str(self.root / "exports")
        os.environ.pop("DINAMIC_INVENTORY_CONTEXT_PATH", None)
        os.environ.pop("DINAMIC_INVENTORY_ID", None)
        os.environ.pop("DINAMIC_BACKEND_URL", None)
        os.environ.pop("DINAMIC_DEVICE_TOKEN", None)
        os.environ.pop("DINAMIC_BACKEND_BEARER_TOKEN", None)
        os.environ.pop("DINAMIC_BACKEND_TOKEN", None)

    def tearDown(self) -> None:
        for key in (
            "DINAMIC_EXPORT_DIRECTORY",
            "DINAMIC_INVENTORY_CONTEXT_PATH",
            "DINAMIC_INVENTORY_ID",
            "DINAMIC_BACKEND_URL",
            "DINAMIC_DEVICE_TOKEN",
            "DINAMIC_BACKEND_BEARER_TOKEN",
            "DINAMIC_BACKEND_TOKEN",
        ):
            os.environ.pop(key, None)

    def _config(self, inventory_id: str, aisle_id: str, *, client_id: str | None = "client-a") -> InventoryOperationalConfig:
        payload: dict[str, object] = {
            "inventory_id": inventory_id,
            "aisles": [{"aisle_id": aisle_id, "aisle_code": "A1"}],
        }
        if client_id:
            payload["client_id"] = client_id
        return InventoryOperationalConfig.from_dict(payload)

    def test_missing_cache_without_backend_is_offline_error_not_not_found(self) -> None:
        with self.assertRaises(InventoryContextError) as ctx:
            load_inventory_operational_config()
        self.assertEqual(ctx.exception.code, "INVENTORY_CONTEXT_UNAVAILABLE_OFFLINE")
        self.assertNotEqual(ctx.exception.code, "INVENTORY_CONTEXT_NOT_FOUND")

    def test_missing_cache_online_without_selection_requires_inventory(self) -> None:
        os.environ["DINAMIC_BACKEND_URL"] = "https://inventory.example.com"
        os.environ["DINAMIC_DEVICE_TOKEN"] = "device-token"
        with self.assertRaises(InventoryContextError) as ctx:
            load_inventory_operational_config()
        self.assertEqual(ctx.exception.code, "INVENTORY_SELECTION_REQUIRED")

    def test_start_without_env_or_cache_syncs_selected_inventory(self) -> None:
        os.environ["DINAMIC_BACKEND_URL"] = "https://inventory.example.com"
        os.environ["DINAMIC_DEVICE_TOKEN"] = "device-token"
        expected = self._config("inventory-selected", "aisle-selected")
        seen: list[str] = []

        class FakeClient:
            def fetch_operational_config(self, inventory_id: str, **_kwargs) -> InventoryOperationalConfig:
                seen.append(inventory_id)
                return expected

        with patch(
            "config.inventory_context_sync.InventoryContextBackendClient",
            return_value=FakeClient(),
        ):
            resolved = resolve_inventory_aisle_for_capture(
                "A1",
                inventory_id="inventory-selected",
                client_id="client-a",
            )
        self.assertEqual(seen, ["inventory-selected"])
        self.assertEqual(resolved.inventory_id, "inventory-selected")
        self.assertEqual(resolved.aisle_id, "aisle-selected")
        persisted = InventoryContextRepository(inventory_context_path()).load()
        assert persisted is not None
        self.assertEqual(persisted.inventory_id, "inventory-selected")
        self.assertEqual(persisted.client_id, "client-a")

    def test_cached_context_is_used_when_backend_unavailable(self) -> None:
        InventoryContextRepository(inventory_context_path()).save(
            self._config("inventory-cached", "aisle-cached")
        )
        os.environ["DINAMIC_BACKEND_URL"] = "https://inventory.example.com"
        os.environ["DINAMIC_DEVICE_TOKEN"] = "device-token"

        class FakeClient:
            def fetch_operational_config(self, _inventory_id: str, **_kwargs) -> InventoryOperationalConfig:
                from config.inventory_context_sync import InventoryContextSyncError

                raise InventoryContextSyncError(
                    "backend unavailable",
                    code="INVENTORY_CONTEXT_UNAVAILABLE_OFFLINE",
                )

        with patch(
            "config.inventory_context_sync.InventoryContextBackendClient",
            return_value=FakeClient(),
        ):
            resolved = resolve_inventory_aisle_for_capture("A1", client_id="client-a")
        self.assertEqual(resolved.inventory_id, "inventory-cached")
        self.assertEqual(resolved.aisle_id, "aisle-cached")

    def test_changing_inventory_replaces_cached_aisle_bindings(self) -> None:
        InventoryContextRepository(inventory_context_path()).save(
            self._config("inventory-old", "aisle-old")
        )
        os.environ["DINAMIC_BACKEND_URL"] = "https://inventory.example.com"
        os.environ["DINAMIC_DEVICE_TOKEN"] = "device-token"
        expected = self._config("inventory-new", "aisle-new")

        class FakeClient:
            def fetch_operational_config(self, inventory_id: str, **_kwargs) -> InventoryOperationalConfig:
                self.last = inventory_id
                return expected

        client = FakeClient()
        with patch(
            "config.inventory_context_sync.InventoryContextBackendClient",
            return_value=client,
        ):
            resolved = resolve_inventory_aisle_for_capture(
                "A1",
                inventory_id="inventory-new",
                client_id="client-a",
            )
        self.assertEqual(client.last, "inventory-new")
        self.assertEqual(resolved.inventory_id, "inventory-new")
        self.assertEqual(resolved.aisle_id, "aisle-new")
        persisted = InventoryContextRepository(inventory_context_path()).load()
        assert persisted is not None
        self.assertEqual(persisted.inventory_id, "inventory-new")
        self.assertNotEqual(persisted.aisles[0][1], "aisle-old")

    def test_offline_does_not_reuse_previous_inventory_cache(self) -> None:
        InventoryContextRepository(inventory_context_path()).save(
            self._config("inventory-old", "aisle-old")
        )
        with self.assertRaises(InventoryContextError) as ctx:
            resolve_inventory_aisle_for_capture(
                "A1",
                inventory_id="inventory-new",
                client_id="client-a",
            )
        self.assertEqual(ctx.exception.code, "INVENTORY_CONTEXT_UNAVAILABLE_OFFLINE")

    def test_offline_does_not_reuse_cache_from_another_client(self) -> None:
        InventoryContextRepository(inventory_context_path()).save(
            self._config("inventory-old", "aisle-old", client_id="client-a")
        )
        with self.assertRaises(InventoryContextError) as ctx:
            load_inventory_operational_config(client_id="client-b")
        self.assertEqual(ctx.exception.code, "INVENTORY_CONTEXT_UNAVAILABLE_OFFLINE")

    def test_sync_does_not_require_env_inventory_id(self) -> None:
        os.environ["DINAMIC_BACKEND_URL"] = "https://inventory.example.com"
        os.environ["DINAMIC_DEVICE_TOKEN"] = "device-token"
        expected = self._config("inventory-selected", "aisle-selected")

        class FakeClient:
            def fetch_operational_config(self, inventory_id: str, **_kwargs) -> InventoryOperationalConfig:
                return expected

        with patch(
            "config.inventory_context_sync.InventoryContextBackendClient",
            return_value=FakeClient(),
        ):
            config = sync_inventory_context_from_backend(
                inventory_id="inventory-selected",
                expected_client_id="client-a",
            )
        self.assertEqual(config.inventory_id, "inventory-selected")
        self.assertFalse(os.environ.get("DINAMIC_INVENTORY_ID"))

    def test_url_without_device_token_is_not_offline(self) -> None:
        os.environ["DINAMIC_BACKEND_URL"] = "https://inventory.example.com"
        os.environ.pop("DINAMIC_DEVICE_TOKEN", None)
        with self.assertRaises(InventoryContextError) as ctx:
            load_inventory_operational_config(inventory_id="inventory-selected")
        self.assertEqual(ctx.exception.code, "INVENTORY_CONTEXT_SYNC_NOT_CONFIGURED")

    def test_admin_bearer_alone_does_not_authenticate_inventory_sync(self) -> None:
        os.environ["DINAMIC_BACKEND_URL"] = "https://inventory.example.com"
        os.environ["DINAMIC_BACKEND_BEARER_TOKEN"] = "admin-token"
        os.environ.pop("DINAMIC_DEVICE_TOKEN", None)
        with self.assertRaises(InventoryContextError) as ctx:
            load_inventory_operational_config(inventory_id="inventory-selected")
        self.assertEqual(ctx.exception.code, "INVENTORY_CONTEXT_SYNC_NOT_CONFIGURED")

    def test_invalid_device_token_does_not_fall_back_to_cache(self) -> None:
        InventoryContextRepository(inventory_context_path()).save(
            self._config("inventory-cached", "aisle-cached")
        )
        os.environ["DINAMIC_BACKEND_URL"] = "https://inventory.example.com"
        os.environ["DINAMIC_DEVICE_TOKEN"] = "invalid-token"

        class FakeClient:
            def fetch_operational_config(self, _inventory_id: str, **_kwargs) -> InventoryOperationalConfig:
                from config.inventory_context_sync import InventoryContextSyncError

                raise InventoryContextSyncError(
                    "backend returned HTTP 401",
                    http_status=401,
                    code="INVENTORY_CONTEXT_AUTH_FAILED",
                )

        with patch(
            "config.inventory_context_sync.InventoryContextBackendClient",
            return_value=FakeClient(),
        ):
            with self.assertRaises(InventoryContextError) as ctx:
                load_inventory_operational_config(
                    inventory_id="inventory-cached",
                    client_id="client-a",
                )
        self.assertEqual(ctx.exception.code, "INVENTORY_CONTEXT_AUTH_FAILED")


if __name__ == "__main__":
    unittest.main()
