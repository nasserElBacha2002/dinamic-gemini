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
from scan_semantics import build_scan_semantics


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
