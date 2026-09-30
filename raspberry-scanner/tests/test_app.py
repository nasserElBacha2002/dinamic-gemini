import io
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import make_handler
from capture import CaptureService
from scanner_service import Reading, ScannerSession


class FakeConfigService:
    def status(self):
        return {}


class FakeRecognition:
    def selection(self):
        return {"selection_mode": "ALL", "client_id": "client-a", "supplier_id": None}


class CaptureDownloadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = Path(tempfile.mkdtemp())
        self.capture = CaptureService(FakeRecognition(), self.directory)
        self.handler_class = make_handler(
            ScannerSession(None),
            FakeConfigService(),
            FakeRecognition(),
            self.capture,
            self.directory,
        )

    def get(self, path: str = "/api/capture/download") -> tuple[int, dict[str, str], bytes]:
        handler = object.__new__(self.handler_class)
        headers: dict[str, str] = {}
        status: list[int] = []
        body = io.BytesIO()
        handler.path = path
        handler.wfile = body
        handler.send_response = lambda value: status.append(int(value))
        handler.send_header = lambda key, value: headers.__setitem__(key.lower(), value)
        handler.end_headers = lambda: None
        handler.do_GET()
        return status[0], headers, body.getvalue()

    def finish_export(self, aisle_code: str = "A01") -> tuple[str, bytes]:
        self.capture.start(aisle_code)
        self.capture.record(Reading(1, "POSITION|POS1|04|RIGHT", 0, {
            "accepted": True,
            "classification": "RAW",
            "recognition": {"selection_mode": "ALL"},
        }))
        snapshot = self.capture.finish()
        filename = snapshot["filename"]
        assert isinstance(filename, str)
        return filename, (self.directory / filename).read_bytes()

    def test_download_without_finished_export_is_controlled_not_found(self) -> None:
        status, headers, body = self.get()

        self.assertEqual(status, 404)
        self.assertEqual(headers["content-type"], "application/json; charset=utf-8")
        self.assertEqual(body, b'{"error": "capture_download_unavailable"}')

    def test_download_returns_exact_persisted_bytes_and_attachment_filename(self) -> None:
        filename, persisted = self.finish_export("PASILLO_04")

        status, headers, body = self.get()

        self.assertEqual(status, 200)
        self.assertEqual(body, persisted)
        self.assertEqual(headers["content-type"], "text/plain; charset=utf-8")
        self.assertIn(f'filename="{filename}"', headers["content-disposition"])
        self.assertEqual(headers["content-length"], str(len(persisted)))

    def test_download_does_not_serve_a_temporary_file_when_final_file_is_missing(self) -> None:
        filename, _ = self.finish_export()
        (self.directory / filename).unlink()
        temporary = self.directory / f".{filename}.temporary"
        temporary.write_bytes(b"partial")

        status, _, body = self.get()

        self.assertEqual(status, 404)
        self.assertNotEqual(body, b"partial")

    def test_download_ignores_client_supplied_paths_and_serves_only_snapshot_file(self) -> None:
        _, persisted = self.finish_export()
        (self.directory / "other.txt").write_bytes(b"other")

        for supplied_path in ("/etc/passwd", "../archivo", "../../archivo", "other.txt"):
            with self.subTest(supplied_path=supplied_path):
                status, _, body = self.get(f"/api/capture/download?path={supplied_path}")
                self.assertEqual(status, 200)
                self.assertEqual(body, persisted)


if __name__ == "__main__":
    unittest.main()
