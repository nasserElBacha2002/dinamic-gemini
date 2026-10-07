import io
import json
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_root))
sys.path.insert(0, str(_root / "tests"))

from config.inventory_catalog import InventoryCatalogRepository, default_catalog_path
from app import make_handler
from capture import CaptureService
from camera import FakeCamera
from capture_session_store import CaptureSessionStore
from config.offline_package import OfflinePackageError, OfflinePackageImporter
from config.repository import SnapshotRepository
from config.service import ConfigService
from recognition import RecognitionService
from recognition_config_bundle_fixture import sample_recognition_config_bundle
from scanner_service import ScannerSession


def _sample_recognition_snapshot_dict() -> dict:
    return {
        "bundle_schema_version": 1,
        "generated_at": "2026-01-15T12:00:00+00:00",
        "bundle_revision": "rev-initial",
        "clients": [
            {
                "client_id": "client-a",
                "name": "Client A",
                "bundle_revision": "client-rev-a",
                "suppliers": [
                    {
                        "client_supplier_id": "supplier-a",
                        "name": "Supplier A",
                        "item_source": "DINAMIC",
                        "position_source": "DINAMIC",
                    }
                ],
                "profiles": [],
            }
        ],
    }


def _sample_package(
    *,
    client_id: str = "client-a",
    inventory_id: str = "inv-1",
    extra_inventory_id: str | None = None,
) -> dict:
    bundle = sample_recognition_config_bundle()
    bundle["inventory_id"] = inventory_id
    bundle["client_id"] = client_id
    inventories = [
        {
            "id": inventory_id,
            "name": "Warehouse 1",
            "client_id": client_id,
            "status": "draft",
        }
    ]
    configs = [bundle]
    if extra_inventory_id:
        extra_bundle = sample_recognition_config_bundle()
        extra_bundle["inventory_id"] = extra_inventory_id
        extra_bundle["client_id"] = client_id
        inventories.append(
            {
                "id": extra_inventory_id,
                "name": "Warehouse 2",
                "client_id": client_id,
                "status": "draft",
            }
        )
        configs.append(extra_bundle)
    return {
        "package_schema_version": 1,
        "generated_at": "2026-03-01T12:00:00+00:00",
        "recognition": _sample_recognition_snapshot_dict(),
        "inventories": inventories,
        "inventory_recognition_configs": configs,
    }


class OfflinePackageImportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp())
        os.environ["DINAMIC_EXPORT_DIRECTORY"] = str(self.root / "exports")
        os.environ["DINAMIC_CONFIG_PATH"] = str(self.root / "recognition-config.json")
        os.environ["DINAMIC_INVENTORY_CATALOG_PATH"] = str(self.root / "inventory-catalog.json")
        self.snapshot_repo = SnapshotRepository(Path(os.environ["DINAMIC_CONFIG_PATH"]))
        self.catalog_repo = InventoryCatalogRepository(default_catalog_path())
        self.importer = OfflinePackageImporter(self.snapshot_repo, self.catalog_repo)

    def tearDown(self) -> None:
        for key in (
            "DINAMIC_EXPORT_DIRECTORY",
            "DINAMIC_CONFIG_PATH",
            "DINAMIC_INVENTORY_CATALOG_PATH",
        ):
            os.environ.pop(key, None)

    def test_import_new_entities(self) -> None:
        raw = json.dumps(_sample_package()).encode("utf-8")
        outcome = self.importer.import_json_bytes(raw)
        self.assertEqual(outcome.clients_added, 1)
        self.assertEqual(outcome.inventories_added, 1)
        self.assertEqual(outcome.contexts_added, 1)
        snapshot = self.snapshot_repo.load()
        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot.client("client-a").name, "Client A")
        catalog = self.catalog_repo.load()
        self.assertIn("inv-1", catalog.inventories)
        self.assertIn("inv-1", catalog.contexts)

    def test_reimport_is_idempotent_counts(self) -> None:
        raw = json.dumps(_sample_package()).encode("utf-8")
        self.importer.import_json_bytes(raw)
        outcome = self.importer.import_json_bytes(raw)
        self.assertEqual(outcome.clients_updated, 1)
        self.assertEqual(outcome.inventories_updated, 1)
        self.assertEqual(outcome.contexts_updated, 1)
        self.assertEqual(outcome.clients_added, 0)
        catalog = self.catalog_repo.load()
        self.assertEqual(len(catalog.inventories), 1)

    def test_import_does_not_delete_local_entities_missing_from_json(self) -> None:
        first = _sample_package()
        second = _sample_package(inventory_id="inv-2", extra_inventory_id=None)
        self.importer.import_json_bytes(json.dumps(first).encode("utf-8"))
        self.importer.import_json_bytes(json.dumps(second).encode("utf-8"))
        catalog = self.catalog_repo.load()
        self.assertIn("inv-1", catalog.inventories)
        self.assertIn("inv-2", catalog.inventories)

    def test_invalid_json_does_not_mutate_state(self) -> None:
        valid = json.dumps(_sample_package()).encode("utf-8")
        self.importer.import_json_bytes(valid)
        before = self.snapshot_repo.load()
        with self.assertRaises(OfflinePackageError):
            self.importer.import_json_bytes(b"{not-json")
        after = self.snapshot_repo.load()
        self.assertEqual(before.as_dict(), after.as_dict())

    def test_catalog_lists_imported_inventories_offline(self) -> None:
        self.importer.import_json_bytes(json.dumps(_sample_package()).encode("utf-8"))
        rows = self.catalog_repo.list_for_client("client-a")
        self.assertEqual([row.inventory_id for row in rows], ["inv-1"])

    def test_imported_inventories_listable_via_api_offline(self) -> None:
        self.importer.import_json_bytes(json.dumps(_sample_package()).encode("utf-8"))
        os.environ.pop("DINAMIC_BACKEND_URL", None)
        os.environ.pop("DINAMIC_DEVICE_TOKEN", None)
        config_service = ConfigService(self.snapshot_repo, None)
        recognition = RecognitionService(config_service)
        store = CaptureSessionStore(self.root / "sessions")
        capture = CaptureService(
            recognition,
            self.root / "exports",
            camera=FakeCamera(),
            session_store=store,
            photos_root=self.root / "photos",
        )
        handler_class = make_handler(
            ScannerSession(None),
            config_service,
            recognition,
            capture,
            self.root / "exports",
            offline_package_importer=self.importer,
        )
        handler = object.__new__(handler_class)
        status: list[int] = []
        body = io.BytesIO()
        handler.path = "/api/inventories?client_id=client-a"
        handler.wfile = body
        handler.headers = {"Content-Length": "0"}
        handler.send_response = lambda value: status.append(int(value))
        handler.send_header = lambda key, value: None
        handler.end_headers = lambda: None
        handler.do_GET()
        payload = json.loads(body.getvalue().decode("utf-8"))
        self.assertEqual(status[0], 200)
        self.assertEqual(payload["source"], "catalog")
        self.assertEqual(payload["items"][0]["id"], "inv-1")

    def test_catalog_replace_failure_restores_prior_snapshot(self) -> None:
        seed = _sample_package()
        self.importer.import_json_bytes(json.dumps(seed).encode("utf-8"))
        before_snapshot = self.importer._snapshot_repository.load()
        before_catalog = self.importer._catalog_repository.load()
        assert before_snapshot is not None

        original_replace = os.replace

        def flaky_replace(src, dst, *args, **kwargs):
            if Path(dst) == self.catalog_repo.path:
                raise OSError("catalog replace failed")
            return original_replace(src, dst, *args, **kwargs)

        with patch("config.offline_package.os.replace", side_effect=flaky_replace):
            with self.assertRaises(OSError):
                self.importer.import_json_bytes(json.dumps(_sample_package()).encode("utf-8"))

        after_snapshot = self.importer._snapshot_repository.load()
        after_catalog = self.importer._catalog_repository.load()
        self.assertEqual(before_snapshot.as_dict(), after_snapshot.as_dict())
        self.assertEqual(before_catalog.as_dict(), after_catalog.as_dict())

    def test_concurrent_imports_are_serialized(self) -> None:
        active = 0
        max_active = 0
        counter_lock = threading.Lock()

        original_atomic = __import__(
            "config.offline_package", fromlist=["_atomic_replace_pair"]
        )._atomic_replace_pair

        def slow_atomic(**kwargs):
            nonlocal active, max_active
            with counter_lock:
                active += 1
                max_active = max(max_active, active)
            try:
                original_atomic(**kwargs)
            finally:
                with counter_lock:
                    active -= 1

        raw = json.dumps(_sample_package()).encode("utf-8")
        errors: list[BaseException] = []

        def run_import() -> None:
            try:
                self.importer.import_json_bytes(raw)
            except BaseException as exc:
                errors.append(exc)

        with patch("config.offline_package._atomic_replace_pair", side_effect=slow_atomic):
            threads = [threading.Thread(target=run_import) for _ in range(3)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

        self.assertEqual(errors, [])
        self.assertEqual(max_active, 1)

    def test_client_update_replaces_recognition_client(self) -> None:
        package = _sample_package()
        self.importer.import_json_bytes(json.dumps(package).encode("utf-8"))
        updated = _sample_package()
        updated["recognition"]["clients"][0]["name"] = "Client A renamed"
        self.importer.import_json_bytes(json.dumps(updated).encode("utf-8"))
        snapshot = self.snapshot_repo.load()
        assert snapshot is not None
        self.assertEqual(snapshot.client("client-a").name, "Client A renamed")


if __name__ == "__main__":
    unittest.main()
