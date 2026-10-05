"""Session export ZIP fixtures (mobile package_version 2, not offline aisle).

CSV bytes should come from ``local_csv_mobile_contract_v1.MOBILE_CSV_CONTRACT_V1`` or
``_csv_bytes`` in package envelope tests — do not re-encode mobile row builders here.
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile

JPEG_MINIMAL = (
    b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    b"\xff\xd9"
)


def legacy_v2_manifest(
    *,
    export_id: str,
    inventory_id: str,
    aisle_id: str,
    capture_session_id: str,
    csv_checksum_sha256: str,
    freeze_id: str = "freeze-1",
    row_count: int = 1,
    expected_photo_count: int = 1,
    included_photo_count: int = 1,
    exported_at: str = "2026-08-04T10:00:00Z",
    photos: list[dict[str, object]],
    package_checksum_sha256: str = "abc",
    omit_legacy_ids: bool = False,
) -> dict[str, object]:
    """Manifest shape accepted by legacy v2 validators (ids mirror CSV when present)."""
    base: dict[str, object] = {
        "schema_version": "1.1",
        "package_kind": "DINAMIC_LOCAL_AISLE_EXPORT",
        "package_version": 2,
        "status": "COMPLETE",
        "freeze_id": freeze_id,
        "freeze_generation": 1,
        "row_count": row_count,
        "expected_photo_count": expected_photo_count,
        "included_photo_count": included_photo_count,
        "missing_photos": [],
        "csv_checksum_sha256": csv_checksum_sha256,
        "checksum_sha256": csv_checksum_sha256,
        "checksum_algorithm": "sha256",
        "package_checksum_sha256": package_checksum_sha256,
        "summary": {
            "photo_count": included_photo_count,
            "position_event_count": 0,
            "product_result_count": 1,
            "rejected_detection_count": 0,
        },
        "photos": photos,
    }
    if not omit_legacy_ids:
        base["export_id"] = export_id
        base["exported_at"] = exported_at
        base["inventory_id"] = inventory_id
        base["aisle_id"] = aisle_id
        base["capture_session_id"] = capture_session_id
    return base


def write_session_zip(
    *,
    csv_bytes: bytes,
    manifest: dict[str, object],
    photo_id: str,
    photo_bytes: bytes = JPEG_MINIMAL,
) -> bytes:
    file_name = f"0001_{photo_id}.jpg"
    sha = hashlib.sha256(photo_bytes).hexdigest()
    photos = manifest.get("photos")
    if isinstance(photos, list) and photos and isinstance(photos[0], dict):
        photos[0].setdefault("sha256", sha)
        photos[0].setdefault("size_bytes", len(photo_bytes))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_STORED) as zf:
        zf.writestr("results.csv", csv_bytes)
        zf.writestr("manifest.json", json.dumps(manifest))
        zf.writestr(f"photos/{file_name}", photo_bytes)
    return buf.getvalue()
