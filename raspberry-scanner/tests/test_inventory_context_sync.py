import email.message
import io
import json
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.inventory_context_sync import (
    InventoryContextBackendClient,
    InventoryContextSyncError,
    operational_config_from_recognition_bundle,
)
from recognition_config_bundle_fixture import sample_recognition_config_bundle


class _JsonUrlResponse:
    def __init__(self, payload: dict) -> None:
        self._body = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "_JsonUrlResponse":
        return self

    def __exit__(self, *_args: object) -> None:
        return None


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

    def test_list_inventories_parses_backend_scoped_items(self) -> None:
        pages = [
            {
                "items": [
                    {"id": "inv-a", "name": "A", "client_id": "client-a", "status": "draft"},
                    {"id": "inv-b", "name": "B", "client_id": "client-a", "status": "draft"},
                    {"name": "missing-id", "client_id": "client-a"},
                ],
            }
        ]

        class FakeClient(InventoryContextBackendClient):
            def _get_json(self, url: str):
                self.url = url
                return pages[0]

        client = FakeClient("https://inventory.example.com", "device-secret")
        entries = client.list_inventories(client_id="client-a")
        self.assertEqual(
            [(row.inventory_id, row.client_id) for row in entries],
            [("inv-a", "client-a"), ("inv-b", "client-a")],
        )
        self.assertIn("/api/v3/raspberry/inventories", client.url)
        self.assertIn("client_id=client-a", client.url)

    def test_list_inventories_requires_client_id(self) -> None:
        client = InventoryContextBackendClient("https://inventory.example.com", "device-secret")
        with self.assertRaises(InventoryContextSyncError) as ctx:
            client.list_inventories(client_id="")
        self.assertEqual(ctx.exception.code, "INVENTORY_CLIENT_REQUIRED")

    def test_list_inventories_sends_device_token_not_bearer(self) -> None:
        seen: dict[str, object] = {}

        def fake_urlopen(request, timeout=None):
            seen["url"] = request.full_url
            seen["token"] = request.get_header("X-device-token")
            seen["authorization"] = request.get_header("Authorization")
            return _JsonUrlResponse({"items": []})

        client = InventoryContextBackendClient("https://inventory.example.com", "device-secret")
        with patch("urllib.request.urlopen", fake_urlopen):
            entries = client.list_inventories(client_id="client-a")
        self.assertEqual(entries, ())
        self.assertEqual(seen["token"], "device-secret")
        self.assertIsNone(seen["authorization"])
        self.assertEqual(
            seen["url"],
            "https://inventory.example.com/api/v3/raspberry/inventories?client_id=client-a",
        )

    def test_fetch_operational_config_uses_raspberry_device_path(self) -> None:
        seen: dict[str, object] = {}
        bundle = sample_recognition_config_bundle()

        def fake_urlopen(request, timeout=None):
            seen["url"] = request.full_url
            seen["token"] = request.get_header("X-device-token")
            seen["authorization"] = request.get_header("Authorization")
            return _JsonUrlResponse(bundle)

        client = InventoryContextBackendClient("https://inventory.example.com", "device-secret")
        with patch("urllib.request.urlopen", fake_urlopen):
            config = client.fetch_operational_config(
                "inv-uuid-1",
                client_id="client-uuid-1",
            )
        self.assertEqual(config.inventory_id, "inv-uuid-1")
        self.assertEqual(seen["token"], "device-secret")
        self.assertIsNone(seen["authorization"])
        self.assertIn(
            "/api/v3/raspberry/inventories/inv-uuid-1/recognition-config",
            str(seen["url"]),
        )
        self.assertIn("client_id=client-uuid-1", str(seen["url"]))

    def test_http_401_is_auth_failed_not_offline(self) -> None:
        def fake_urlopen(request, timeout=None):
            raise urllib.error.HTTPError(
                request.full_url,
                401,
                "Unauthorized",
                email.message.Message(),
                io.BytesIO(b""),
            )

        client = InventoryContextBackendClient("https://inventory.example.com", "bad-token")
        with patch("urllib.request.urlopen", fake_urlopen):
            with self.assertRaises(InventoryContextSyncError) as ctx:
                client.list_inventories(client_id="client-a")
        self.assertEqual(ctx.exception.code, "INVENTORY_CONTEXT_AUTH_FAILED")
        self.assertEqual(ctx.exception.http_status, 401)

    def test_network_error_is_offline(self) -> None:
        def fake_urlopen(request, timeout=None):
            raise urllib.error.URLError("connection refused")

        client = InventoryContextBackendClient("https://inventory.example.com", "device-secret")
        with patch("urllib.request.urlopen", fake_urlopen):
            with self.assertRaises(InventoryContextSyncError) as ctx:
                client.list_inventories(client_id="client-a")
        self.assertEqual(ctx.exception.code, "INVENTORY_CONTEXT_UNAVAILABLE_OFFLINE")


class BackendSnapshotClientRegressionTests(unittest.TestCase):
    def test_clients_snapshot_still_uses_device_token(self) -> None:
        from config.sync import BackendSnapshotClient, SnapshotSyncError

        seen: dict[str, object] = {}

        def fake_urlopen(request, timeout=None):
            seen["url"] = request.full_url
            seen["token"] = request.get_header("X-device-token")
            raise urllib.error.HTTPError(
                request.full_url,
                401,
                "Unauthorized",
                email.message.Message(),
                io.BytesIO(b""),
            )

        client = BackendSnapshotClient("https://inventory.example.com", "device-secret")
        with patch("urllib.request.urlopen", fake_urlopen):
            with self.assertRaises(SnapshotSyncError):
                client.fetch()
        self.assertEqual(
            seen["url"],
            "https://inventory.example.com/api/v3/raspberry/recognition-config",
        )
        self.assertEqual(seen["token"], "device-secret")


if __name__ == "__main__":
    unittest.main()
