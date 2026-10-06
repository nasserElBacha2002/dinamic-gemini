import email.message
import io
import json
import os
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import make_handler
from capture import CaptureService
from camera import FakeCamera
from capture_session_store import CaptureSessionStore
from inventory_context import InventoryOperationalConfig, inventory_context_path
from config.inventory_context_repository import InventoryContextRepository
from config.inventory_context_sync import InventoryContextSyncError
from scanner_service import ScannerSession


class FakeConfigService:
    def status(self):
        return {}

    def clients(self):
        return [{"client_id": "client-a", "name": "Client A"}]

    def client_config(self, client_id):
        if client_id != "client-a":
            return None
        return {"client_id": "client-a", "name": "Client A"}

    def suppliers(self, client_id):
        if client_id != "client-a":
            return []
        return [{"client_supplier_id": "supplier-a", "name": "Supplier A"}]

    def supplier_config(self, client_id, supplier_id):
        if client_id != "client-a" or supplier_id != "supplier-a":
            return None
        return {"client_supplier_id": "supplier-a", "name": "Supplier A"}


class FakeRecognition:
    def selection(self):
        return {"selection_mode": "ALL", "client_id": "client-a", "supplier_id": None}

    def select(self, client_id, supplier_id, *, scanning):
        return self.selection()


class _JsonUrlResponse:
    def __init__(self, payload: dict) -> None:
        self._body = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "_JsonUrlResponse":
        return self

    def __exit__(self, *_args: object) -> None:
        return None


class InventorySelectionApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp())
        os.environ["DINAMIC_EXPORT_DIRECTORY"] = str(self.root / "exports")
        os.environ.pop("DINAMIC_INVENTORY_CONTEXT_PATH", None)
        os.environ.pop("DINAMIC_INVENTORY_ID", None)
        os.environ.pop("DINAMIC_BACKEND_BEARER_TOKEN", None)
        os.environ.pop("DINAMIC_BACKEND_TOKEN", None)
        os.environ["DINAMIC_BACKEND_URL"] = "https://inventory.example.com"
        os.environ["DINAMIC_DEVICE_TOKEN"] = "device-secret"
        self.store = CaptureSessionStore(self.root / "sessions")
        self.capture = CaptureService(
            FakeRecognition(),
            self.root / "exports",
            camera=FakeCamera(),
            session_store=self.store,
            photos_root=self.root / "photos",
        )
        self.handler_class = make_handler(
            ScannerSession(None),
            FakeConfigService(),
            FakeRecognition(),
            self.capture,
            self.root / "exports",
            package_session_store=self.store,
            package_photos_root=self.root / "photos",
            package_export_directory=self.root / "packages",
            package_upload_store=None,
        )

    def tearDown(self) -> None:
        for key in (
            "DINAMIC_EXPORT_DIRECTORY",
            "DINAMIC_INVENTORY_ID",
            "DINAMIC_BACKEND_URL",
            "DINAMIC_DEVICE_TOKEN",
            "DINAMIC_BACKEND_BEARER_TOKEN",
            "DINAMIC_BACKEND_TOKEN",
        ):
            os.environ.pop(key, None)

    def _request(self, method: str, path: str, payload: dict | None = None) -> tuple[int, dict]:
        handler = object.__new__(self.handler_class)
        status: list[int] = []
        body = io.BytesIO()
        handler.path = path
        handler.wfile = body
        handler.headers = {"Content-Length": "0"}
        handler.send_response = lambda value: status.append(int(value))
        handler.send_header = lambda key, value: None
        handler.end_headers = lambda: None
        if payload is not None:
            encoded = json.dumps(payload).encode("utf-8")
            handler.headers = {"Content-Length": str(len(encoded))}
            handler.rfile = io.BytesIO(encoded)
        if method == "GET":
            handler.do_GET()
        else:
            handler.do_POST()
        raw = body.getvalue()
        return status[0], json.loads(raw.decode("utf-8")) if raw else {}

    def test_state_exposes_missing_inventory_context_without_failing(self) -> None:
        status, payload = self._request("GET", "/api/state")
        self.assertEqual(status, 200)
        self.assertFalse(payload["inventory_context"]["available"])
        self.assertIsNone(payload["inventory_context"]["inventory_id"])

    def test_clients_and_suppliers_remain_available(self) -> None:
        status, payload = self._request("GET", "/api/config/clients")
        self.assertEqual(status, 200)
        self.assertEqual(payload["items"][0]["client_id"], "client-a")
        status, payload = self._request("GET", "/api/config/clients/client-a/suppliers")
        self.assertEqual(status, 200)
        self.assertEqual(payload["items"][0]["client_supplier_id"], "supplier-a")

    def test_post_inventory_context_persists_backend_inventory(self) -> None:
        expected = InventoryOperationalConfig.from_dict(
            {
                "inventory_id": "inventory-selected",
                "client_id": "client-a",
                "aisles": [{"aisle_id": "aisle-selected", "aisle_code": "A1"}],
            }
        )

        class FakeClient:
            def fetch_operational_config(self, inventory_id: str, **_kwargs) -> InventoryOperationalConfig:
                self.seen = inventory_id
                return expected

        client = FakeClient()
        with patch(
            "config.inventory_context_sync.InventoryContextBackendClient",
            return_value=client,
        ):
            status, payload = self._request(
                "POST",
                "/api/inventory-context",
                {"inventory_id": "inventory-selected"},
            )
        self.assertEqual(status, 200)
        self.assertEqual(payload["inventory_id"], "inventory-selected")
        self.assertEqual(client.seen, "inventory-selected")
        status, state = self._request("GET", "/api/inventory-context")
        self.assertEqual(status, 200)
        self.assertTrue(state["available"])
        self.assertEqual(state["inventory_id"], "inventory-selected")

    def test_get_inventories_uses_device_token_without_admin_bearer(self) -> None:
        os.environ.pop("DINAMIC_BACKEND_BEARER_TOKEN", None)
        os.environ.pop("DINAMIC_BACKEND_TOKEN", None)
        seen: dict[str, object] = {}

        def fake_urlopen(request, timeout=None):
            seen["url"] = request.full_url
            seen["token"] = request.get_header("X-device-token")
            seen["authorization"] = request.get_header("Authorization")
            return _JsonUrlResponse(
                {
                    "items": [
                        {
                            "id": "inv-a",
                            "name": "A",
                            "client_id": "client-a",
                            "status": "draft",
                        }
                    ]
                }
            )

        with patch("urllib.request.urlopen", fake_urlopen):
            status, payload = self._request("GET", "/api/inventories?client_id=client-a")
        self.assertEqual(status, 200)
        self.assertEqual(payload["source"], "backend")
        self.assertEqual(payload["items"][0]["id"], "inv-a")
        self.assertIn("/api/v3/raspberry/inventories", str(seen["url"]))
        self.assertIn("client_id=client-a", str(seen["url"]))
        self.assertNotIn("/api/v3/inventories/", str(seen["url"]))
        self.assertEqual(seen["token"], "device-secret")
        self.assertIsNone(seen["authorization"])

    def test_get_inventories_invalid_device_token_is_auth_error_not_offline(self) -> None:
        def fake_urlopen(request, timeout=None):
            raise urllib.error.HTTPError(
                request.full_url,
                401,
                "Unauthorized",
                email.message.Message(),
                io.BytesIO(b'{"detail":"Invalid Raspberry device token"}'),
            )

        with patch("urllib.request.urlopen", fake_urlopen):
            status, payload = self._request("GET", "/api/inventories?client_id=client-a")
        self.assertEqual(status, 401)
        self.assertEqual(payload["error"], "INVENTORY_CONTEXT_AUTH_FAILED")
        self.assertNotEqual(payload["error"], "INVENTORY_CONTEXT_UNAVAILABLE_OFFLINE")
        self.assertEqual(payload["source"], "unavailable")
        self.assertEqual(payload["items"], [])

    def test_get_inventories_falls_back_to_cache_when_backend_offline(self) -> None:
        InventoryContextRepository(inventory_context_path()).save(
            InventoryOperationalConfig.from_dict(
                {
                    "inventory_id": "inventory-cached",
                    "client_id": "client-a",
                    "aisles": [{"aisle_id": "aisle-cached", "aisle_code": "A1"}],
                }
            )
        )

        class FakeClient:
            def list_inventories(self, *, client_id):
                raise InventoryContextSyncError(
                    "backend unavailable",
                    code="INVENTORY_CONTEXT_UNAVAILABLE_OFFLINE",
                )

        with patch("app.InventoryContextBackendClient", return_value=FakeClient()):
            status, payload = self._request("GET", "/api/inventories?client_id=client-a")
        self.assertEqual(status, 200)
        self.assertEqual(payload["source"], "cache")
        self.assertEqual(payload["items"][0]["id"], "inventory-cached")

    def test_get_inventories_empty_backend_list_is_valid(self) -> None:
        class FakeClient:
            def list_inventories(self, *, client_id):
                self.client_id = client_id
                return ()

        client = FakeClient()
        with patch("app.InventoryContextBackendClient", return_value=client):
            status, payload = self._request("GET", "/api/inventories?client_id=client-a")
        self.assertEqual(status, 200)
        self.assertEqual(payload["source"], "backend")
        self.assertEqual(payload["items"], [])
        self.assertEqual(client.client_id, "client-a")

    def test_get_inventories_without_device_token_is_not_offline(self) -> None:
        os.environ.pop("DINAMIC_DEVICE_TOKEN", None)
        os.environ["DINAMIC_BACKEND_BEARER_TOKEN"] = "admin-token"
        status, payload = self._request("GET", "/api/inventories?client_id=client-a")
        self.assertEqual(status, 401)
        self.assertEqual(payload["error"], "INVENTORY_CONTEXT_SYNC_NOT_CONFIGURED")
        self.assertNotEqual(payload["error"], "INVENTORY_CONTEXT_UNAVAILABLE_OFFLINE")

    def test_capture_start_without_env_or_prior_cache_binds_selected_inventory(self) -> None:
        expected = InventoryOperationalConfig.from_dict(
            {
                "inventory_id": "inventory-selected",
                "client_id": "client-a",
                "aisles": [{"aisle_id": "aisle-selected", "aisle_code": "A1"}],
            }
        )

        class FakeClient:
            def fetch_operational_config(self, inventory_id: str, **_kwargs) -> InventoryOperationalConfig:
                return expected

        with patch(
            "config.inventory_context_sync.InventoryContextBackendClient",
            return_value=FakeClient(),
        ):
            snapshot = self.capture.start("A1", inventory_id="inventory-selected")
        self.assertEqual(snapshot["state"], "ACTIVE")
        stored = self.store.load_session(str(snapshot["capture_session_id"]))
        assert stored is not None
        self.assertEqual(stored.inventory_id, "inventory-selected")
        self.assertEqual(stored.aisle_id, "aisle-selected")
        persisted = InventoryContextRepository(inventory_context_path()).load()
        assert persisted is not None
        self.assertEqual(persisted.inventory_id, "inventory-selected")


if __name__ == "__main__":
    unittest.main()
