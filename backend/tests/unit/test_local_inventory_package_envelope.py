"""Package envelope authority: results.csv canonical, manifest legacy-compatible."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import zipfile

import pytest

from src.application.services.local_inventory_package_parser import (
    LocalInventoryPackageError,
    parse_local_inventory_package,
)
from tests.fixtures.local_csv_mobile_contract_v1 import MOBILE_CSV_CONTRACT_V1
from tests.fixtures.session_export_mobile_package_v2 import (
    JPEG_MINIMAL,
    legacy_v2_manifest,
    write_session_zip,
)
from tests.unit.test_local_inventory_package import HEADERS, _build_zip, _csv_bytes


def _photo_meta(photo_id: str, client_file_id: str) -> dict[str, object]:
    file_name = f"0001_{photo_id}.jpg"
    return {
        "capture_photo_id": photo_id,
        "client_file_id": client_file_id,
        "sequence_number": 1,
        "file_name": file_name,
        "mime_type": "image/jpeg",
        "size_bytes": len(JPEG_MINIMAL),
        "sha256": hashlib.sha256(JPEG_MINIMAL).hexdigest(),
        "width": 1,
        "height": 1,
        "asset_variant": "ORIGINAL",
    }


def test_historical_manifest_and_csv_consistent_ids() -> None:
    parsed = parse_local_inventory_package(_build_zip())
    assert parsed.export_id == "export-pkg-1"
    assert parsed.inventory_id == "inventory-1"
    assert parsed.aisle_id == "aisle-1"
    assert parsed.capture_session_id == "session-1"


def test_slim_manifest_csv_carries_ids() -> None:
    export_id = "export-slim"
    csv_bytes = _csv_bytes(export_id=export_id, photo_id="p-slim", client_file_id="cf-slim")
    checksum = hashlib.sha256(csv_bytes).hexdigest()
    manifest = legacy_v2_manifest(
        export_id=export_id,
        inventory_id="inventory-1",
        aisle_id="aisle-1",
        capture_session_id="session-1",
        csv_checksum_sha256=checksum,
        photos=[_photo_meta("p-slim", "cf-slim")],
        omit_legacy_ids=True,
    )
    parsed = parse_local_inventory_package(
        write_session_zip(csv_bytes=csv_bytes, manifest=manifest, photo_id="p-slim")
    )
    assert parsed.export_id == export_id
    assert parsed.inventory_id == "inventory-1"


def test_mobile_contract_csv_with_v2_manifest_fixture() -> None:
    csv_bytes = MOBILE_CSV_CONTRACT_V1
    checksum = hashlib.sha256(csv_bytes).hexdigest()
    manifest = legacy_v2_manifest(
        export_id="export-contract-1",
        inventory_id="inventory-1",
        aisle_id="aisle-1",
        capture_session_id="session-1",
        csv_checksum_sha256=checksum,
        photos=[_photo_meta("photo-1", "file-1")],
    )
    parsed = parse_local_inventory_package(
        write_session_zip(csv_bytes=csv_bytes, manifest=manifest, photo_id="photo-1")
    )
    assert parsed.export_id == "export-contract-1"
    assert parsed.inventory_id == "inventory-1"


@pytest.mark.parametrize(
    ("field", "manifest_value"),
    [
        ("export_id", "export-wrong"),
        ("inventory_id", "inventory-wrong"),
        ("aisle_id", "aisle-wrong"),
        ("capture_session_id", "session-wrong"),
    ],
)
def test_rejects_manifest_csv_mismatch(field: str, manifest_value: str) -> None:
    csv_bytes = _csv_bytes()
    checksum = hashlib.sha256(csv_bytes).hexdigest()
    manifest = legacy_v2_manifest(
        export_id="export-pkg-1",
        inventory_id="inventory-1",
        aisle_id="aisle-1",
        capture_session_id="session-1",
        csv_checksum_sha256=checksum,
        photos=[_photo_meta("photo-1", "file-1")],
    )
    manifest[field] = manifest_value
    with pytest.raises(LocalInventoryPackageError) as exc:
        parse_local_inventory_package(
            write_session_zip(csv_bytes=csv_bytes, manifest=manifest, photo_id="photo-1")
        )
    assert exc.value.code == "PACKAGE_ENVELOPE_MISMATCH"


def test_rejects_csv_without_data_rows() -> None:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=HEADERS, lineterminator="\r\n")
    writer.writeheader()
    csv_bytes = output.getvalue().encode()
    checksum = hashlib.sha256(csv_bytes).hexdigest()
    manifest = legacy_v2_manifest(
        export_id="export-pkg-1",
        inventory_id="inventory-1",
        aisle_id="aisle-1",
        capture_session_id="session-1",
        csv_checksum_sha256=checksum,
        photos=[_photo_meta("photo-1", "file-1")],
    )
    with pytest.raises(LocalInventoryPackageError) as exc:
        parse_local_inventory_package(
            write_session_zip(csv_bytes=csv_bytes, manifest=manifest, photo_id="photo-1")
        )
    assert exc.value.code == "PACKAGE_CSV_ENVELOPE_EMPTY"


def test_rejects_malformed_csv_for_envelope() -> None:
    csv_bytes = b"schema_version,export_id\n\"unclosed\n"
    manifest = {
        "package_kind": "DINAMIC_LOCAL_AISLE_EXPORT",
        "package_version": 2,
        "status": "COMPLETE",
        "export_id": "e1",
        "inventory_id": "i1",
        "expected_photo_count": 0,
        "included_photo_count": 0,
        "photos": [],
        "csv_checksum_sha256": hashlib.sha256(csv_bytes).hexdigest(),
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_STORED) as zf:
        zf.writestr("results.csv", csv_bytes)
        zf.writestr("manifest.json", json.dumps(manifest))
    with pytest.raises(LocalInventoryPackageError) as exc:
        parse_local_inventory_package(buf.getvalue())
    assert exc.value.code == "PACKAGE_CSV_MALFORMED"


def test_rejects_non_utf8_csv_for_envelope() -> None:
    csv_bytes = b"\xff\xfe"
    manifest = {
        "package_kind": "DINAMIC_LOCAL_AISLE_EXPORT",
        "package_version": 2,
        "status": "COMPLETE",
        "export_id": "e1",
        "inventory_id": "i1",
        "expected_photo_count": 0,
        "included_photo_count": 0,
        "photos": [],
        "csv_checksum_sha256": hashlib.sha256(csv_bytes).hexdigest(),
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_STORED) as zf:
        zf.writestr("results.csv", csv_bytes)
        zf.writestr("manifest.json", json.dumps(manifest))
    with pytest.raises(LocalInventoryPackageError) as exc:
        parse_local_inventory_package(buf.getvalue())
    assert exc.value.code == "PACKAGE_CSV_INVALID_ENCODING"


def test_rejects_freeze_id_mismatch_when_csv_column_present() -> None:
    output = io.StringIO(newline="")
    headers = list(HEADERS) + ["freeze_id"]
    writer = csv.DictWriter(output, fieldnames=headers, lineterminator="\r\n")
    writer.writeheader()
    base_row = {
        "schema_version": "1",
        "export_id": "export-pkg-1",
        "exported_at": "2026-08-04T10:00:00Z",
        "device_id": "device-1",
        "inventory_id": "inventory-1",
        "aisle_id": "aisle-1",
        "capture_session_id": "session-1",
        "capture_photo_id": "photo-1",
        "client_file_id": "file-1",
        "capture_order": "1",
        "captured_at": "2026-08-04T09:59:00Z",
        "position_code": "A-01",
        "internal_code": "SKU-1",
        "quantity": "7",
        "quantity_status": "PRESENT",
        "detection_status": "DETECTED",
        "source": "LOCAL_CODE_SCAN",
        "requires_review": "false",
        "error_code": "",
        "notes": "ok",
        "freeze_id": "freeze-csv",
    }
    writer.writerow(base_row)
    csv_bytes = output.getvalue().encode()
    checksum = hashlib.sha256(csv_bytes).hexdigest()
    manifest = legacy_v2_manifest(
        export_id="export-pkg-1",
        inventory_id="inventory-1",
        aisle_id="aisle-1",
        capture_session_id="session-1",
        csv_checksum_sha256=checksum,
        freeze_id="freeze-manifest",
        photos=[_photo_meta("photo-1", "file-1")],
    )
    with pytest.raises(LocalInventoryPackageError) as exc:
        parse_local_inventory_package(
            write_session_zip(csv_bytes=csv_bytes, manifest=manifest, photo_id="photo-1")
        )
    assert exc.value.code == "PACKAGE_ENVELOPE_MISMATCH"


def test_historical_csv_extra_columns_still_resolves_envelope() -> None:
    """Wide legacy CSV rows (extra columns) remain compatible when ids match manifest."""
    output = io.StringIO(newline="")
    wide_headers = list(HEADERS) + ["inventory_name", "freeze_id", "position_status"]
    writer = csv.DictWriter(output, fieldnames=wide_headers, lineterminator="\r\n")
    writer.writeheader()
    row = {
        "schema_version": "1.1",
        "export_id": "export-wide",
        "exported_at": "2026-08-04T10:00:00Z",
        "device_id": "device-1",
        "inventory_id": "inventory-1",
        "aisle_id": "aisle-1",
        "capture_session_id": "session-1",
        "capture_photo_id": "photo-wide",
        "client_file_id": "file-wide",
        "capture_order": "1",
        "captured_at": "2026-08-04T09:59:00Z",
        "position_code": "A-01",
        "internal_code": "SKU-1",
        "quantity": "1",
        "quantity_status": "PRESENT",
        "detection_status": "DETECTED",
        "source": "LOCAL_CODE_SCAN",
        "requires_review": "false",
        "error_code": "",
        "notes": "",
        "inventory_name": "Inv",
        "freeze_id": "freeze-legacy",
        "position_status": "FROM_SNAPSHOT",
    }
    writer.writerow(row)
    csv_bytes = output.getvalue().encode()
    checksum = hashlib.sha256(csv_bytes).hexdigest()
    manifest = legacy_v2_manifest(
        export_id="export-wide",
        inventory_id="inventory-1",
        aisle_id="aisle-1",
        capture_session_id="session-1",
        csv_checksum_sha256=checksum,
        freeze_id="freeze-legacy",
        photos=[_photo_meta("photo-wide", "file-wide")],
    )
    parsed = parse_local_inventory_package(
        write_session_zip(csv_bytes=csv_bytes, manifest=manifest, photo_id="photo-wide")
    )
    assert parsed.export_id == "export-wide"
    assert parsed.freeze_id == "freeze-legacy"
