"""HTTP API for creating local provisional inventories."""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import make_handler
from capture import CaptureService
from config.inventory_catalog import InventoryCatalogRepository, default_catalog_path
from scanner_service import ScannerSession


class FakeConfigService:
    def status(self):
        return {}


class FakeRecognition:
    def selection(self):
        return {"selection_mode": "ALL", "client_id": "client-a", "supplier_id": None}


class LocalInventoryApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp())
        os.environ["DINAMIC_EXPORT_DIRECTORY"] = str(self.root / "exports")
        os.environ["DINAMIC_INVENTORY_CATALOG_PATH"] = str(self.root / "inventory-catalog.json")
        self.capture = CaptureService(FakeRecognition(), self.root / "exports")
        self.handler_class = make_handler(
            ScannerSession(None),
            FakeConfigService(),
            FakeRecognition(),
            self.capture,
            self.root / "exports",
        )

    def tearDown(self) -> None:
        os.environ.pop("DINAMIC_EXPORT_DIRECTORY", None)
        os.environ.pop("DINAMIC_INVENTORY_CATALOG_PATH", None)

    def _post(self, path: str, payload: dict) -> tuple[int, dict]:
        handler = object.__new__(self.handler_class)
        status: list[int] = []
        body = io.BytesIO()
        encoded = json.dumps(payload).encode("utf-8")
        handler.path = path
        handler.wfile = body
        handler.headers = {"Content-Length": str(len(encoded))}
        handler.rfile = io.BytesIO(encoded)
        handler.send_response = lambda value: status.append(int(value))
        handler.send_header = lambda key, value: None
        handler.end_headers = lambda: None
        handler.do_POST()
        raw = body.getvalue()
        return status[0], json.loads(raw.decode("utf-8"))

    def test_create_local_inventory_persists_catalog(self) -> None:
        status, payload = self._post(
            "/api/inventories/local",
            {"client_id": "client-a", "name": "Stock depósito"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["client_id"], "client-a")
        self.assertEqual(payload["status"], "local_provisional")
        inventory_id = payload["inventory_id"]
        entry = InventoryCatalogRepository(default_catalog_path()).load().inventories[
            inventory_id
        ]
        self.assertEqual(entry.name, "Stock depósito")

    def test_create_local_inventory_requires_name(self) -> None:
        status, payload = self._post("/api/inventories/local", {"client_id": "client-a", "name": ""})
        self.assertEqual(status, 400)
        self.assertEqual(payload["error"], "INVENTORY_NAME_REQUIRED")