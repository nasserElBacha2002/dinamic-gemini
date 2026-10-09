"""Canonical position code length coherence for Phase 4 corrections."""

from __future__ import annotations

import csv
import io
import unicodedata

from src.application.services.local_csv_parser import parse_local_csv
from src.application.services.position_recognition.normalization import (
    CANONICAL_POSITION_CODE_MAX_LENGTH,
    normalize_position_code,
)


def _csv_bytes(position_code: str) -> bytes:
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "schema_version",
            "export_id",
            "inventory_id",
            "device_id",
            "exported_at",
            "aisle_id",
            "capture_session_id",
            "capture_photo_id",
            "client_file_id",
            "capture_order",
            "captured_at",
            "position_code",
            "internal_code",
            "quantity",
            "quantity_status",
            "detection_status",
            "source",
            "requires_review",
            "error_code",
            "notes",
        ],
    )
    writer.writeheader()
    writer.writerow(
        {
            "schema_version": "1",
            "export_id": "export-len-1",
            "inventory_id": "inventory-1",
            "device_id": "device-1",
            "exported_at": "2026-08-04T10:00:00Z",
            "aisle_id": "aisle-1",
            "capture_session_id": "session-1",
            "capture_photo_id": "photo-1",
            "client_file_id": "file-1",
            "capture_order": "1",
            "captured_at": "2026-08-04T09:59:00Z",
            "position_code": position_code,
            "internal_code": "SKU-1",
            "quantity": "1",
            "quantity_status": "PRESENT",
            "detection_status": "DETECTED",
            "source": "LOCAL_CODE_SCAN",
            "requires_review": "false",
            "error_code": "",
            "notes": "",
        }
    )
    return output.getvalue().encode()


def test_canonical_max_length_is_64() -> None:
    assert CANONICAL_POSITION_CODE_MAX_LENGTH == 64


def test_accepts_63_and_64_rejects_65() -> None:
    assert normalize_position_code("A" * 63).normalized_code == "A" * 63
    assert normalize_position_code("A" * 64).normalized_code == "A" * 64
    parsed_ok = parse_local_csv(_csv_bytes("P" * 64))
    assert parsed_ok.rows[0].errors == ()
    parsed_bad = parse_local_csv(_csv_bytes("P" * 65))
    assert "position_code:position_code_too_long" in parsed_bad.rows[0].errors


def test_does_not_silently_truncate_spaces_or_unicode() -> None:
    spaced = "  " + ("B" * 64) + "  "
    normalized = normalize_position_code(spaced).normalized_code
    assert len(normalized) <= CANONICAL_POSITION_CODE_MAX_LENGTH
    assert normalized == "B" * 64

    nfd = unicodedata.normalize("NFD", "Café" + ("X" * 60))
    nfc = unicodedata.normalize("NFC", nfd)
    if len(nfc) > CANONICAL_POSITION_CODE_MAX_LENGTH:
        parsed = parse_local_csv(_csv_bytes(nfd))
        assert any("too_long" in e for e in parsed.rows[0].errors)
    else:
        assert len(normalize_position_code(nfd).normalized_code) == len(nfc)


def test_supplementary_plane_counted_as_python_chars() -> None:
    code = "A" * 63 + "𐍈"
    assert len(code) == 64
    assert normalize_position_code(code).normalized_code == code
    too_long = "A" * 64 + "𐍈"
    parsed = parse_local_csv(_csv_bytes(too_long))
    assert "position_code:position_code_too_long" in parsed.rows[0].errors
