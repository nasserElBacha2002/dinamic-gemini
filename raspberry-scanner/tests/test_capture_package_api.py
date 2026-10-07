import io
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from app import make_handler
from capture import CaptureService
from camera import FakeCamera
from capture_session_store import CaptureSessionStore
from inventory_context_fixture import install_test_inventory_context
from package_upload_store import PackageUploadStore
from scanner_service import ScannerSession
from test_session_package_export import FakeRecognition, item_reading, position_reading
from session_package_upload import PackageUploadError
from test_session_package_upload import (
    RecordingBackendClient,
    _confirm_response,
    _preview_response,
)

from src.domain.product_labels.format import build_product_label_payload


class FakeConfigService:
    def status(self):
        return {}


class FakeRecognition:
    def selection(self):
        return {"selection_mode": "ALL", "client_id": "client-a", "supplier_id": None}


class CapturePackageApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp())
        install_test_inventory_context(self.root)
        self.export_dir = self.root / "exports"
        self.store = CaptureSessionStore(self.root / "sessions")
        self.photos_root = self.root / "photos"
        self.upload_store = PackageUploadStore(self.root / "upload-state")
        self.capture = CaptureService(
            FakeRecognition(),
            self.export_dir,
            camera=FakeCamera(),
            session_store=self.store,
            photos_root=self.photos_root,
        )
        self.handler_class = make_handler(
            ScannerSession(None),
            FakeConfigService(),
            FakeRecognition(),
            self.capture,
            self.export_dir,
            package_session_store=self.store,
            package_photos_root=self.photos_root,
            package_export_directory=self.root / "packages",
            package_upload_store=self.upload_store,
        )

    def _request(self, method: str, path: str) -> tuple[int, bytes]:
        handler = object.__new__(self.handler_class)
        status: list[int] = []
        body = io.BytesIO()
        handler.path = path
        handler.wfile = body
        handler.send_response = lambda value: status.append(int(value))
        handler.send_header = lambda key, value: None
        handler.end_headers = lambda: None
        if method == "GET":
            handler.do_GET()
        else:
            handler.do_POST()
        return status[0], body.getvalue()

    def _request_download(self) -> tuple[int, dict[str, str], bytes]:
        handler = object.__new__(self.handler_class)
        headers: dict[str, str] = {}
        status: list[int] = []
        body = io.BytesIO()
        handler.path = "/api/capture/download"
        handler.wfile = body
        handler.send_response = lambda value: status.append(int(value))
        handler.send_header = lambda key, value: headers.__setitem__(key.lower(), value)
        handler.end_headers = lambda: None
        handler.do_GET()
        return status[0], headers, body.getvalue()

    def test_get_export_and_upload_do_not_mutate(self) -> None:
        for path in ("/api/capture/export", "/api/capture/upload"):
            status, body = self._request("GET", path)
            self.assertEqual(status, 405, path)
            self.assertIn(b"method_not_allowed", body)

    def test_post_export_requires_finished_session(self) -> None:
        status, body = self._request("POST", "/api/capture/export")
        self.assertEqual(status, 409)
        self.assertIn(b"capture_not_finished", body)

    def _finish_capture_session(self) -> str:
        valid = build_product_label_payload(
            label_id="A1B2C3D4E5",
            internal_code="SKU",
            quantity=2,
        )
        self.capture.start("A1")
        self.capture.record(position_reading(1))
        self.capture.record(item_reading(2, valid))
        self.capture.wait_for_photo_pipeline_idle()
        session_id = self.capture.snapshot()["capture_session_id"]
        assert isinstance(session_id, str)
        self.capture.finish()
        return session_id

    def _start_capture_with_photos(self) -> str:
        valid = build_product_label_payload(
            label_id="A1B2C3D4E5",
            internal_code="SKU",
            quantity=2,
        )
        self.capture.start("A1")
        self.capture.record(position_reading(1))
        self.capture.record(item_reading(2, valid))
        self.capture.wait_for_photo_pipeline_idle()
        session_id = self.capture.snapshot()["capture_session_id"]
        assert isinstance(session_id, str)
        return session_id

    def test_finish_exports_zip_with_photos_and_download_serves_zip(self) -> None:
        session_id = self._start_capture_with_photos()
        photos_dir = self.photos_root / session_id
        jpgs = sorted(photos_dir.glob("*.jpg"))
        self.assertGreaterEqual(len(jpgs), 1)
        status, body = self._request("POST", "/api/capture/finish")
        self.assertEqual(status, 200)
        payload = json.loads(body.decode("utf-8"))
        self.assertEqual(payload["state"], "FINISHED")
        self.assertEqual(payload["capture_session_id"], session_id)
        filename = payload["filename"]
        self.assertIsInstance(filename, str)
        self.assertTrue(filename.endswith(".zip"))
        self.assertEqual(payload["package_filename"], filename)
        zip_path = self.root / "packages" / filename
        self.assertTrue(zip_path.is_file())
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
        for photo in jpgs:
            self.assertIn(f"photos/{photo.name}", names)
        download_status, headers, download_body = self._request_download()
        self.assertEqual(download_status, 200)
        self.assertEqual(headers["content-type"], "application/zip")
        self.assertIn(f'filename="{filename}"', headers["content-disposition"])
        self.assertEqual(download_body, zip_path.read_bytes())
        state_status, state_body = self._request("GET", "/api/state")
        self.assertEqual(state_status, 200)
        state = json.loads(state_body.decode("utf-8"))
        self.assertEqual(state["capture"]["filename"], filename)
        self.assertEqual(state["capture"]["package_filename"], filename)

    def test_finish_does_not_succeed_when_package_export_fails(self) -> None:
        self._start_capture_with_photos()
        with patch(
            "app.ensure_session_package_exported",
            side_effect=PackageUploadError("EXPORT_FAILED_TEST", "package boom"),
        ):
            status, body = self._request("POST", "/api/capture/finish")
        self.assertEqual(status, 409)
        payload = json.loads(body.decode("utf-8"))
        self.assertEqual(payload["error"], "EXPORT_FAILED_TEST")
        self.assertEqual(self.capture.snapshot()["state"], "EXPORT_FAILED")
        download_status, _, download_body = self._request_download()
        self.assertEqual(download_status, 404)
        self.assertIn(b"capture_download_unavailable", download_body)

    def test_post_export_happy_path(self) -> None:
        session_id = self._finish_capture_session()
        status, body = self._request("POST", "/api/capture/export")
        self.assertEqual(status, 200)
        payload = json.loads(body.decode("utf-8"))
        self.assertEqual(payload["capture_session_id"], session_id)
        self.assertTrue(payload.get("export_id"))
        self.assertTrue(Path(str(payload["zip_path"])).is_file())

    def test_post_upload_happy_path_without_real_network(self) -> None:
        session_id = self._finish_capture_session()
        export_status, export_body = self._request("POST", "/api/capture/export")
        self.assertEqual(export_status, 200)
        export_id = json.loads(export_body.decode("utf-8"))["export_id"]
        client = RecordingBackendClient(
            preview=_preview_response(export_id=str(export_id)),
            confirm=_confirm_response(export_id=str(export_id)),
        )
        with patch(
            "app.build_backend_client_from_environment",
            return_value=client,
        ):
            status, body = self._request("POST", "/api/capture/upload")
        self.assertEqual(status, 200)
        payload = json.loads(body.decode("utf-8"))
        self.assertEqual(payload["capture_session_id"], session_id)
        self.assertEqual(payload["upload_state"], "CONFIRMED")
        self.assertEqual(len(client.preview_calls), 1)
        self.assertEqual(len(client.confirm_calls), 1)


if __name__ == "__main__":
    unittest.main()
