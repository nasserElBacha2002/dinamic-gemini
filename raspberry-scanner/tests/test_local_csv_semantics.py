import sys
import tempfile
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
sys.modules.setdefault("pyodbc", types.ModuleType("pyodbc"))

from capture_session_store import CaptureSessionState, PhotoCaptureRecord
from local_csv_rows import build_local_csv_rows
from scan_semantics import ScanSemantics, build_scan_semantics, position_from_snapshot


class LocalCsvSemanticsTests(unittest.TestCase):
    def _session(self) -> CaptureSessionState:
        return CaptureSessionState(
            capture_session_id="session-1",
            aisle_code="A1",
            state="FINISHED",
            selection={},
            started_at="2026-01-01T00:00:00Z",
            inventory_id="inventory-1",
            aisle_id="aisle-1",
        )

    def _photo(
        self,
        *,
        sequence: int,
        decision: dict,
        raw: str,
        export_line: str,
    ) -> PhotoCaptureRecord:
        semantics = build_scan_semantics(raw, decision, export_line=export_line)
        assert semantics is not None
        return PhotoCaptureRecord(
            capture_photo_id=f"photo-{sequence}",
            sequence_number=sequence,
            scanner_sequence=sequence,
            export_line=export_line,
            status="COMPLETE",
            captured_at="2026-01-01T00:00:01Z",
            file_name=f"{sequence:04d}.jpg",
            photo_sha256="a" * 64,
            photo_size_bytes=10,
            scan_semantics=semantics.to_dict(),
        )

    def test_dinamic_item_row(self) -> None:
        from src.domain.product_labels.format import build_product_label_payload

        valid = build_product_label_payload(label_id="A1B2C3D4E5", internal_code="SKU", quantity=2)
        decision = {
            "accepted": True,
            "classification": "ITEM",
            "recognition": {
                "selection_mode": "SPECIFIC",
                "results": {
                    "ITEM": {
                        "status": "VALID",
                        "source": "DINAMIC",
                        "label_id": "A1B2C3D4E5",
                        "internal_code": "SKU",
                        "quantity": 2,
                    }
                },
            },
        }
        photos = [self._photo(sequence=1, decision=decision, raw=valid, export_line=valid)]
        built = build_local_csv_rows(
            self._session(),
            complete_photos=photos,
            inventory_id="inventory-1",
            aisle_id="aisle-1",
            device_id="device",
            export_id="export-1",
            exported_at="2026-01-01T00:00:02Z",
        )
        self.assertEqual(built.rows[0]["source"], "LOCAL_CODE_SCAN")
        self.assertEqual(built.rows[0]["label_id"], "A1B2C3D4E5")

    def test_all_mode_preserves_simple_raw(self) -> None:
        raw = "PLAIN-SKU-ONLY"
        decision = {
            "accepted": True,
            "classification": "RAW",
            "recognition": {"selection_mode": "ALL"},
        }
        photos = [self._photo(sequence=1, decision=decision, raw=raw, export_line=raw)]
        built = build_local_csv_rows(
            self._session(),
            complete_photos=photos,
            inventory_id="inventory-1",
            aisle_id="aisle-1",
            device_id="device",
            export_id="export-all-simple",
            exported_at="2026-01-01T00:00:02Z",
        )
        self.assertEqual(built.rows[0]["internal_code"], raw)
        self.assertEqual(built.rows[0]["source"], "LOCAL_CODE_SCAN")

    def test_supplier_item_row_from_snapshot_without_d1_parse(self) -> None:
        raw = "SUP|SKU|3"
        snapshot = (
            '{"client_supplier_id":"sup-1","item":{"status":"VALID",'
            '"label_id":"LBL-SUP","sku":"SKU-SUP","quantity":3}}'
        )
        semantics = ScanSemantics(
            classification="ITEM",
            selection_mode="SPECIFIC",
            raw_payload=raw,
            export_line=raw,
            client_id="client-a",
            supplier_id="sup-1",
            item_source="SUPPLIER",
            position_source="DINAMIC",
            recognition_snapshot_json=snapshot,
        )
        photos = [
            PhotoCaptureRecord(
                capture_photo_id="photo-1",
                sequence_number=1,
                scanner_sequence=1,
                export_line=raw,
                status="COMPLETE",
                captured_at="2026-01-01T00:00:01Z",
                file_name="0001.jpg",
                photo_sha256="a" * 64,
                photo_size_bytes=10,
                scan_semantics=semantics.to_dict(),
            )
        ]
        built = build_local_csv_rows(
            self._session(),
            complete_photos=photos,
            inventory_id="inventory-1",
            aisle_id="aisle-1",
            device_id="device",
            export_id="export-sup-item",
            exported_at="2026-01-01T00:00:02Z",
        )
        self.assertEqual(len(built.rows), 1)
        self.assertEqual(built.rows[0]["label_id"], "LBL-SUP")
        self.assertEqual(built.rows[0]["internal_code"], "SKU-SUP")
        self.assertEqual(built.rows[0]["quantity"], "3")
        self.assertEqual(built.rows[0]["source"], "LOCAL_CODE_SCAN")

    def test_all_mode_preserves_raw_with_pipe(self) -> None:
        raw = "SEG|SKU|2|EXTRA"
        decision = {
            "accepted": True,
            "classification": "RAW",
            "recognition": {"selection_mode": "ALL"},
        }
        photos = [self._photo(sequence=1, decision=decision, raw=raw, export_line=raw)]
        built = build_local_csv_rows(
            self._session(),
            complete_photos=photos,
            inventory_id="inventory-1",
            aisle_id="aisle-1",
            device_id="device",
            export_id="export-all",
            exported_at="2026-01-01T00:00:02Z",
        )
        self.assertEqual(built.rows[0]["internal_code"], raw)
        self.assertEqual(built.rows[0]["source"], "LOCAL_CODE_SCAN")

    def test_supplier_position_preserves_raw_payload(self) -> None:
        raw = "RAW-SUPPLIER|with|pipes"
        snapshot = (
            '{"client_supplier_id":"sup-1","position":{"status":"VALID",'
            '"position_id":"NORM-ID","normalized_payload":"NORM-ID","pallet":"1","side":"LEFT"}}'
        )
        parsed = position_from_snapshot(snapshot, raw_payload=raw)
        assert parsed is not None
        self.assertEqual(parsed["position_payload_raw"], raw)
        self.assertEqual(parsed["position_code"], "NORM-ID")
        self.assertNotEqual(parsed["position_payload_raw"], "NORM-ID|1|LEFT")

    def test_duplicate_item_does_not_emit_position_row(self) -> None:
        from src.domain.product_labels.format import build_product_label_payload

        valid = build_product_label_payload(label_id="A1B2C3D4E5", internal_code="SKU", quantity=2)
        decision = {
            "accepted": True,
            "classification": "ITEM",
            "recognition": {
                "selection_mode": "SPECIFIC",
                "results": {"ITEM": {"status": "VALID", "source": "DINAMIC"}},
            },
        }
        photos = [
            self._photo(sequence=1, decision=decision, raw=valid, export_line=valid),
            self._photo(sequence=2, decision=decision, raw=valid, export_line=valid),
        ]
        built = build_local_csv_rows(
            self._session(),
            complete_photos=photos,
            inventory_id="inventory-1",
            aisle_id="aisle-1",
            device_id="device",
            export_id="export-dup",
            exported_at="2026-01-01T00:00:02Z",
        )
        self.assertEqual(len(built.rows), 1)
        self.assertEqual(built.rows[0]["source"], "LOCAL_CODE_SCAN")
        self.assertFalse(any(r["source"] == "LOCAL_POSITION_LABEL" for r in built.rows))


if __name__ == "__main__":
    unittest.main()
