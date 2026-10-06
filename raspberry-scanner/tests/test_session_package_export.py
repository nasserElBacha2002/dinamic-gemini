import hashlib
import io
import json
import os
import sys
import tempfile
import types
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
sys.modules.setdefault("pyodbc", types.ModuleType("pyodbc"))

from camera import FakeCamera
from capture import CaptureService
from capture_session_store import CaptureSessionStore, PhotoCaptureRecord
from scanner_service import Reading
from session_package_export import (
    SessionPackageExportContext,
    SessionPackageExportError,
    export_finished_session_package,
)
from inventory_context_fixture import install_test_inventory_context

from src.application.services.local_inventory_package_parser import (
    parse_local_inventory_package,
)
from src.domain.product_labels.format import build_product_label_payload


class FakeRecognition:
    def __init__(self, client_id: str = "client-a", supplier_id: str = "supplier-a") -> None:
        self.value = {
            "selection_mode": "SPECIFIC" if supplier_id else "ALL",
            "client_id": client_id,
            "supplier_id": supplier_id,
        }

    def selection(self):
        return self.value


def position_reading(sequence: int) -> Reading:
    return Reading(sequence, "json-not-exported", 0, {
        "accepted": True,
        "classification": "POSITION",
        "recognition": {"results": {"POSITION": {
            "status": "VALID",
            "source": "DINAMIC",
            "position_id": "POS1",
            "pallet": "04",
            "side": "RIGHT",
        }}},
    })


def item_reading(sequence: int, raw: str) -> Reading:
    return Reading(sequence, raw, 0, {
        "accepted": True,
        "classification": "ITEM",
        "recognition": {"results": {"ITEM": {"status": "VALID", "source": "DINAMIC"}}},
    })


def build_finished_session(root: Path) -> tuple[CaptureService, CaptureSessionStore, Path, str]:
    install_test_inventory_context(root)
    export_dir = root / "exports"
    store = CaptureSessionStore(root / "sessions")
    photos_root = root / "photos"
    capture = CaptureService(
        FakeRecognition(),
        export_dir,
        camera=FakeCamera(),
        session_store=store,
        photos_root=photos_root,
    )
    valid = build_product_label_payload(label_id="A1B2C3D4E5", internal_code="SKU", quantity=2)
    capture.start("A1")
    capture.record(position_reading(1))
    capture.record(item_reading(2, valid))
    capture.wait_for_photo_pipeline_idle()
    session_id = capture.snapshot()["capture_session_id"]
    assert isinstance(session_id, str)
    photos = capture.snapshot()["photos"]
    capture.finish()
    return capture, store, photos_root, session_id


class SessionPackageExportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp())
        install_test_inventory_context(self.root)
        self.out = self.root / "packages"
        self.context = SessionPackageExportContext(
            inventory_id="inventory-1",
            aisle_id="aisle-1",
            device_id="device-rpi-1",
        )

    def test_finished_session_generates_zip_parsed_by_backend(self) -> None:
        _, store, photos_root, session_id = build_finished_session(self.root)
        before = store.load_session(session_id)
        assert before is not None
        result = export_finished_session_package(
            session_store=store,
            photos_root=photos_root,
            output_directory=self.out,
            capture_session_id=session_id,
            context=self.context,
            export_id="export-test-1",
        )
        self.assertTrue(result.zip_path.is_file())
        after = store.load_session(session_id)
        assert after is not None
        self.assertEqual(after.to_dict(), before.to_dict())

        parsed = parse_local_inventory_package(result.zip_path.read_bytes())
        self.assertEqual(parsed.package_kind, "DINAMIC_LOCAL_AISLE_EXPORT")
        self.assertEqual(parsed.package_version, 2)
        self.assertEqual(parsed.status, "COMPLETE")
        self.assertEqual(parsed.export_id, "export-test-1")
        self.assertEqual(parsed.inventory_id, "inventory-1")
        self.assertEqual(parsed.aisle_id, "aisle-1")
        self.assertEqual(parsed.capture_session_id, session_id)
        self.assertEqual(parsed.included_photo_count, 2)

        with zipfile.ZipFile(result.zip_path, "r") as zf:
            self.assertIn("results.csv", zf.namelist())
            self.assertIn("manifest.json", zf.namelist())
            photo_names = [n for n in zf.namelist() if n.startswith("photos/")]
            self.assertEqual(len(photo_names), 2)

    def test_csv_manifest_linked_by_capture_photo_id_and_sequence_order(self) -> None:
        _, store, photos_root, session_id = build_finished_session(self.root)
        result = export_finished_session_package(
            session_store=store,
            photos_root=photos_root,
            output_directory=self.out,
            capture_session_id=session_id,
            context=self.context,
        )
        data = result.zip_path.read_bytes()
        parsed = parse_local_inventory_package(data)
        manifest = parsed.manifest
        photos = manifest["photos"]
        self.assertEqual(len(photos), 2)
        self.assertEqual(photos[0]["sequence_number"], 1)
        self.assertEqual(photos[1]["sequence_number"], 2)
        csv_text = data.decode("latin-1")  # not used for parsing
        with zipfile.ZipFile(io.BytesIO(data), "r") as zf:
            csv_body = zf.read("results.csv").decode("utf-8")
        for photo in photos:
            self.assertIn(photo["capture_photo_id"], csv_body)

    def test_captured_at_preserved_in_csv(self) -> None:
        _, store, photos_root, session_id = build_finished_session(self.root)
        session = store.load_session(session_id)
        assert session is not None
        expected = {p.capture_photo_id: p.captured_at for p in session.photos}
        result = export_finished_session_package(
            session_store=store,
            photos_root=photos_root,
            output_directory=self.out,
            capture_session_id=session_id,
            context=self.context,
        )
        with zipfile.ZipFile(result.zip_path, "r") as zf:
            csv_body = zf.read("results.csv").decode("utf-8")
        for photo_id, captured_at in expected.items():
            self.assertIn(captured_at, csv_body)
            self.assertIn(photo_id, csv_body)

    def test_missing_photo_file_fails_without_publishing_zip(self) -> None:
        _, store, photos_root, session_id = build_finished_session(self.root)
        session = store.load_session(session_id)
        assert session is not None
        photo = session.photos[0]
        assert photo.file_name
        (photos_root / session_id / photo.file_name).unlink()
        with self.assertRaises(SessionPackageExportError):
            export_finished_session_package(
                session_store=store,
                photos_root=photos_root,
                output_directory=self.out,
                capture_session_id=session_id,
                context=self.context,
            )
        self.assertEqual(list(self.out.glob("*.zip")), [])

    def test_incorrect_stored_hash_fails(self) -> None:
        _, store, photos_root, session_id = build_finished_session(self.root)
        session = store.load_session(session_id)
        assert session is not None
        bad = []
        for photo in session.photos:
            bad.append(
                PhotoCaptureRecord(
                    capture_photo_id=photo.capture_photo_id,
                    sequence_number=photo.sequence_number,
                    scanner_sequence=photo.scanner_sequence,
                    export_line=photo.export_line,
                    status=photo.status,
                    captured_at=photo.captured_at,
                    file_name=photo.file_name,
                    photo_sha256="0" * 64,
                    photo_size_bytes=photo.photo_size_bytes,
                    error=photo.error,
                )
            )
        session.photos = bad
        store.save(session)
        with self.assertRaises(SessionPackageExportError) as ctx:
            export_finished_session_package(
                session_store=store,
                photos_root=photos_root,
                output_directory=self.out,
                capture_session_id=session_id,
                context=self.context,
            )
        self.assertEqual(ctx.exception.code, "EXPORT_PHOTO_SHA_MISMATCH")
    def test_active_session_not_exported(self) -> None:
        install_test_inventory_context(self.root)
        store = CaptureSessionStore(self.root / "sessions")
        photos_root = self.root / "photos"
        capture = CaptureService(
            FakeRecognition(),
            self.root / "exports",
            camera=FakeCamera(),
            session_store=store,
            photos_root=photos_root,
        )
        capture.start("A1")
        session_id = capture.snapshot()["capture_session_id"]
        assert isinstance(session_id, str)
        with self.assertRaises(SessionPackageExportError):
            export_finished_session_package(
                session_store=store,
                photos_root=photos_root,
                output_directory=self.out,
                capture_session_id=session_id,
                context=self.context,
            )

    def test_capturing_photo_blocks_export(self) -> None:
        _, store, photos_root, session_id = build_finished_session(self.root)
        session = store.load_session(session_id)
        assert session is not None
        photos = list(session.photos)
        photos[0] = PhotoCaptureRecord(
            capture_photo_id=photos[0].capture_photo_id,
            sequence_number=photos[0].sequence_number,
            scanner_sequence=photos[0].scanner_sequence,
            export_line=photos[0].export_line,
            status="CAPTURING",
            captured_at=photos[0].captured_at,
            file_name=photos[0].file_name,
        )
        session.photos = photos
        session.state = "FINISHED"
        store.save(session)
        with self.assertRaises(SessionPackageExportError):
            export_finished_session_package(
                session_store=store,
                photos_root=photos_root,
                output_directory=self.out,
                capture_session_id=session_id,
                context=self.context,
            )

    def test_photo_failed_blocks_strict_export(self) -> None:
        install_test_inventory_context(self.root)
        store = CaptureSessionStore(self.root / "sessions")
        photos_root = self.root / "photos"
        capture = CaptureService(
            FakeRecognition(),
            self.root / "exports",
            camera=FakeCamera(fail_after=3),
            session_store=store,
            photos_root=photos_root,
        )
        valid = build_product_label_payload(label_id="A1B2C3D4E5", internal_code="SKU", quantity=1)
        valid2 = build_product_label_payload(label_id="B2C3D4E5F6", internal_code="SKU2", quantity=1)
        capture.start("A1")
        capture.record(position_reading(1))
        capture.record(item_reading(2, valid))
        capture.record(item_reading(3, valid2))
        capture.wait_for_photo_pipeline_idle()
        session_id = capture.snapshot()["capture_session_id"]
        assert isinstance(session_id, str)
        capture.finish()
        with self.assertRaises(SessionPackageExportError) as ctx:
            export_finished_session_package(
                session_store=store,
                photos_root=photos_root,
                output_directory=self.out,
                capture_session_id=session_id,
                context=self.context,
            )
        self.assertEqual(ctx.exception.code, "EXPORT_PHOTO_EVIDENCE_FAILED")

    def test_legacy_session_without_durable_binding_blocks_export(self) -> None:
        _, store, photos_root, session_id = build_finished_session(self.root)
        session = store.load_session(session_id)
        assert session is not None
        session.inventory_id = None
        session.aisle_id = None
        store.save(session)
        with self.assertRaises(SessionPackageExportError) as ctx:
            export_finished_session_package(
                session_store=store,
                photos_root=photos_root,
                output_directory=self.out,
                capture_session_id=session_id,
                context=self.context,
            )
        self.assertEqual(ctx.exception.code, "EXPORT_SESSION_INVENTORY_CONTEXT_MISSING")

    def test_export_rejects_context_mismatch(self) -> None:
        _, store, photos_root, session_id = build_finished_session(self.root)
        with self.assertRaises(SessionPackageExportError) as ctx:
            export_finished_session_package(
                session_store=store,
                photos_root=photos_root,
                output_directory=self.out,
                capture_session_id=session_id,
                context=SessionPackageExportContext(
                    inventory_id="inventory-1",
                    aisle_id="other-aisle",
                    device_id="device",
                ),
            )
        self.assertEqual(ctx.exception.code, "EXPORT_SESSION_AISLE_MISMATCH")

    def test_missing_inventory_or_aisle_ids_fail(self) -> None:
        _, store, photos_root, session_id = build_finished_session(self.root)
        with self.assertRaises(SessionPackageExportError):
            export_finished_session_package(
                session_store=store,
                photos_root=photos_root,
                output_directory=self.out,
                capture_session_id=session_id,
                context=SessionPackageExportContext(
                    inventory_id="",
                    aisle_id="aisle-1",
                    device_id="device",
                ),
            )

    def test_repeat_export_generates_new_export_id(self) -> None:
        _, store, photos_root, session_id = build_finished_session(self.root)
        first = export_finished_session_package(
            session_store=store,
            photos_root=photos_root,
            output_directory=self.out,
            capture_session_id=session_id,
            context=self.context,
            export_id="export-a",
        )
        second = export_finished_session_package(
            session_store=store,
            photos_root=photos_root,
            output_directory=self.out,
            capture_session_id=session_id,
            context=self.context,
            export_id="export-b",
        )
        self.assertNotEqual(first.export_id, second.export_id)
        self.assertTrue(first.zip_path.is_file())
        self.assertTrue(second.zip_path.is_file())

    def test_zip_has_no_undeclared_entries(self) -> None:
        _, store, photos_root, session_id = build_finished_session(self.root)
        result = export_finished_session_package(
            session_store=store,
            photos_root=photos_root,
            output_directory=self.out,
            capture_session_id=session_id,
            context=self.context,
        )
        parsed = parse_local_inventory_package(result.zip_path.read_bytes())
        declared = {"results.csv", "manifest.json"} | {
            f"photos/{p.file_name}" for p in parsed.photos
        }
        with zipfile.ZipFile(result.zip_path, "r") as zf:
            self.assertEqual(set(zf.namelist()), declared)

    def test_hashes_match_manifest_and_csv(self) -> None:
        _, store, photos_root, session_id = build_finished_session(self.root)
        result = export_finished_session_package(
            session_store=store,
            photos_root=photos_root,
            output_directory=self.out,
            capture_session_id=session_id,
            context=self.context,
        )
        with zipfile.ZipFile(result.zip_path, "r") as zf:
            csv_bytes = zf.read("results.csv")
            manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
        self.assertEqual(
            manifest["csv_checksum_sha256"],
            hashlib.sha256(csv_bytes).hexdigest(),
        )
        for entry in manifest["photos"]:
            path = f"photos/{entry['file_name']}"
            content = zipfile.ZipFile(result.zip_path, "r").read(path)
            self.assertEqual(entry["sha256"], hashlib.sha256(content).hexdigest())
            self.assertEqual(entry["size_bytes"], len(content))

    def test_atomic_publish_uses_temp_then_final(self) -> None:
        _, store, photos_root, session_id = build_finished_session(self.root)
        seen: list[str] = []
        original_replace = os.replace

        def tracking_replace(src, dst):  # type: ignore[no-untyped-def]
            seen.append(str(src))
            return original_replace(src, dst)

        with patch("session_package_export.os.replace", tracking_replace):
            result = export_finished_session_package(
                session_store=store,
                photos_root=photos_root,
                output_directory=self.out,
                capture_session_id=session_id,
                context=self.context,
            )
        self.assertTrue(result.zip_path.is_file())
        self.assertTrue(any(".A1_" in path for path in seen))


if __name__ == "__main__":
    unittest.main()
