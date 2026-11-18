"""Pi-side provisional inventory + free aisle → ZIP manifest contract."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_TESTS))
sys.path.insert(0, str(_ROOT.parent / "backend"))

from camera import FakeCamera
from capture import CaptureService
from capture_session_store import CaptureSessionStore
from config.inventory_catalog import InventoryCatalogRepository, default_catalog_path
from provisional_ids import PENDING_AISLE_ID, is_pending_aisle_id
from scanner_service import Reading
from session_package_export import export_finished_session_package
from session_package_upload import export_context_for_session
from test_session_package_export import FakeRecognition, item_reading, position_reading

from src.application.services.local_inventory_package_parser import parse_local_inventory_package
from src.domain.product_labels.format import build_product_label_payload


class ProvisionalEndToEndTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp())
        os.environ["DINAMIC_EXPORT_DIRECTORY"] = str(self.root / "exports")
        os.environ["DINAMIC_INVENTORY_CATALOG_PATH"] = str(self.root / "inventory-catalog.json")

    def tearDown(self) -> None:
        for key in ("DINAMIC_EXPORT_DIRECTORY", "DINAMIC_INVENTORY_CATALOG_PATH"):
            os.environ.pop(key, None)

    def test_register_local_inventory_catalog_and_context(self) -> None:
        repo = InventoryCatalogRepository(default_catalog_path())
        entry = repo.register_local_inventory(client_id="client-a", name="Inv local")
        doc = repo.load()
        self.assertEqual(doc.inventories[entry.inventory_id].status, "local_provisional")
        ctx = doc.contexts[entry.inventory_id]
        self.assertEqual(ctx.aisles, ())
        self.assertEqual(ctx.client_id, "client-a")

    def test_capture_export_zip_with_provisional_manifest(self) -> None:
        repo = InventoryCatalogRepository(default_catalog_path())
        entry = repo.register_local_inventory(client_id="client-a", name="Prueba campo")
        export_dir = self.root / "exports"
        store = CaptureSessionStore(self.root / "sessions")
        photos_root = self.root / "photos"
        capture = CaptureService(
            FakeRecognition(),
            export_dir,
            camera=FakeCamera(),
            session_store=store,
            photos_root=photos_root,
        )
        valid = build_product_label_payload(label_id="A1B2C3D4E5", internal_code="SKU", quantity=2)
        capture.start("PASILLO_LIBRE", inventory_id=entry.inventory_id)
        session_id = capture.snapshot()["capture_session_id"]
        assert isinstance(session_id, str)
        active = store.load_session(session_id)
        assert active is not None
        self.assertEqual(active.inventory_id, entry.inventory_id)
        self.assertEqual(active.aisle_id, PENDING_AISLE_ID)
        self.assertTrue(is_pending_aisle_id(active.aisle_id))
        capture.record(position_reading(1))
        capture.record(item_reading(2, valid))
        capture.wait_for_photo_pipeline_idle()
        capture.finish()

        session = store.load_session(session_id)
        assert session is not None
        context = export_context_for_session(session)
        self.assertTrue(context.aisle_provisional)
        self.assertTrue(context.inventory_provisional)
        self.assertEqual(context.inventory_name, "Prueba campo")
        self.assertEqual(context.client_id, "client-a")
        self.assertEqual(context.aisle_code, "PASILLO_LIBRE")

        result = export_finished_session_package(
            session_store=store,
            photos_root=photos_root,
            output_directory=self.root / "packages",
            capture_session_id=session_id,
            context=context,
            export_id="export-e2e-prov",
        )
        parsed = parse_local_inventory_package(result.zip_path.read_bytes())
        self.assertEqual(parsed.inventory_id, entry.inventory_id)
        self.assertEqual(parsed.manifest.get("aisle_code"), "PASILLO_LIBRE")
        self.assertTrue(parsed.manifest.get("aisle_provisional"))
        self.assertTrue(parsed.manifest.get("inventory_provisional"))
        self.assertEqual(parsed.manifest.get("client_id"), "client-a")

        with zipfile.ZipFile(result.zip_path, "r") as zf:
            manifest = json.loads(zf.read("manifest.json"))
            self.assertEqual(manifest["aisle_id"], PENDING_AISLE_ID)

        csv_text = zipfile.ZipFile(result.zip_path, "r").read("results.csv").decode("utf-8")
        self.assertIn(PENDING_AISLE_ID, csv_text)