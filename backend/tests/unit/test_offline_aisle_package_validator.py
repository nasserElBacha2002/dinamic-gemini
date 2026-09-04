"""Unit tests for offline aisle package validator."""

from __future__ import annotations

import hashlib
import io
import json
import zipfile

from src.application.services.offline_aisle_package_validator import (
    OFFLINE_AISLE_FORMAT,
    OFFLINE_AISLE_SCHEMA_VERSION,
    validate_offline_aisle_package_bytes,
)


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _item_provenance(raw: str, profile_id: str = "prof-item", version: int = 10) -> dict:
    return {
        "source": "SUPPLIER",
        "client_supplier_id": "sup-b",
        "profile_id": profile_id,
        "profile_version": version,
        "profile_ref": f"item:{profile_id}:v{version}",
        "raw_evidence": {
            "raw_payload": raw,
            "raw_payload_sha256": _sha256_text(raw),
        },
    }


def _position_provenance(raw: str, profile_id: str = "prof-pos", version: int = 3) -> dict:
    return {
        "source": "SUPPLIER",
        "client_supplier_id": "sup-b",
        "profile_id": profile_id,
        "profile_version": version,
        "profile_ref": f"position:{profile_id}:v{version}",
        "raw_evidence": {
            "raw_payload": raw,
            "raw_payload_sha256": _sha256_text(raw),
        },
    }


def _golden_package() -> bytes:
    aisle = {
        "id": "aisle-golden",
        "inventory_id": "inv-1",
        "client_supplier_id": "sup-b",
        "name": "Pasillo A",
        "created_offline_at": "2026-01-01T00:00:00.000Z",
        "completed_at": None,
        "origin": "LOCAL",
        "sync_status": "LOCAL_ONLY",
    }
    profiles = [
        {
            "profile_ref": "item:prof-item:v10",
            "label_kind": "ITEM",
            "client_supplier_id": "sup-b",
            "source": "SUPPLIER",
            "profile_id": "prof-item",
            "profile_version": 10,
        },
        {
            "profile_ref": "position:prof-pos:v3",
            "label_kind": "POSITION",
            "client_supplier_id": "sup-b",
            "source": "SUPPLIER",
            "profile_id": "prof-pos",
            "profile_version": 3,
        },
    ]
    item_raw = "LPNA000184|SKU773421|24"
    pos_raw = "A04-R-02|04|RIGHT|02"
    item_capture = {
        "capture_id": "cap-item",
        "capture_session_id": "sess-1",
        "aisle_id": "aisle-golden",
        "label_kind": "ITEM",
        "result_kind": "PRODUCT",
        "status": "RESOLVED",
        "error_code": None,
        "requires_review": False,
        "recognitions": {"item": _item_provenance(item_raw), "position": None},
        "result": {
            "product": {"label_id": "LPNA000184", "sku": "SKU773421", "quantity": 24},
            "position": None,
        },
        "asset": {"included": False, "asset_id": "a1", "path": None},
    }
    pos_capture = {
        "capture_id": "cap-pos",
        "capture_session_id": "sess-1",
        "aisle_id": "aisle-golden",
        "label_kind": "POSITION",
        "result_kind": "POSITION_ONLY",
        "status": "DETECTED_UNVERIFIED",
        "error_code": "POSITION_LABEL_DETECTED",
        "requires_review": False,
        "recognitions": {"item": None, "position": _position_provenance(pos_raw)},
        "result": {
            "product": None,
            "position": {
                "position_id": "A04-R-02",
                "pallet": "04",
                "side": "RIGHT",
                "level": "02",
            },
        },
        "asset": {"included": False, "asset_id": "a2", "path": None},
    }
    empty_seg_raw = "A04-R-02|04||02"
    empty_seg_capture = {
        **pos_capture,
        "capture_id": "cap-empty-seg",
        "recognitions": {"item": None, "position": _position_provenance(empty_seg_raw)},
    }
    mixed_capture = {
        "capture_id": "cap-mixed",
        "capture_session_id": "sess-1",
        "aisle_id": "aisle-golden",
        "label_kind": "ITEM",
        "result_kind": "PRODUCT_WITH_POSITION",
        "status": "RESOLVED",
        "error_code": None,
        "requires_review": False,
        "recognitions": {
            "item": _item_provenance(item_raw),
            "position": _position_provenance(pos_raw),
        },
        "result": {
            "product": {"label_id": "LPNA000184", "sku": "SKU773421", "quantity": 24},
            "position": {
                "position_id": "A04-R-02",
                "pallet": "04",
                "side": "RIGHT",
                "level": "02",
            },
        },
        "asset": {"included": False, "asset_id": "a3", "path": None},
    }
    aisle_json = json.dumps(aisle, indent=2) + "\n"
    profiles_json = json.dumps(profiles, indent=2) + "\n"
    item_json = json.dumps(item_capture, indent=2) + "\n"
    pos_json = json.dumps(pos_capture, indent=2) + "\n"
    empty_json = json.dumps(empty_seg_capture, indent=2) + "\n"
    mixed_json = json.dumps(mixed_capture, indent=2) + "\n"
    integrity = {
        "aisle.json": _sha256_text(aisle_json),
        "recognition/profiles.json": _sha256_text(profiles_json),
        "captures/cap-item.json": _sha256_text(item_json),
        "captures/cap-pos.json": _sha256_text(pos_json),
        "captures/cap-empty-seg.json": _sha256_text(empty_json),
        "captures/cap-mixed.json": _sha256_text(mixed_json),
    }
    manifest = {
        "format": OFFLINE_AISLE_FORMAT,
        "schema_version": OFFLINE_AISLE_SCHEMA_VERSION,
        "export_id": "export-golden",
        "created_at": "2026-01-01T00:00:00.000Z",
        "app_version": "0.3.0",
        "inventory": {"id": "inv-1", "name": "Inv", "client_id": "client-1"},
        "aisle": {
            "id": "aisle-golden",
            "name": "Pasillo A",
            "origin": "LOCAL",
            "sync_status": "LOCAL_ONLY",
            "operational_status": "local_completed",
        },
        "supplier": {"client_supplier_id": "sup-b", "name": "pruebas b"},
        "capture_count": 4,
        "asset_count": 0,
        "include_assets": False,
        "completeness": "COMPLETE",
        "integrity": {"algorithm": "sha256", "files": integrity},
    }
    manifest_json = json.dumps(manifest, indent=2) + "\n"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("manifest.json", manifest_json)
        zf.writestr("aisle.json", aisle_json)
        zf.writestr("recognition/profiles.json", profiles_json)
        zf.writestr("captures/cap-item.json", item_json)
        zf.writestr("captures/cap-pos.json", pos_json)
        zf.writestr("captures/cap-empty-seg.json", empty_json)
        zf.writestr("captures/cap-mixed.json", mixed_json)
    return buf.getvalue()


def test_validate_golden_package_ok() -> None:
    result = validate_offline_aisle_package_bytes(_golden_package())
    assert result.ok is True
    assert result.errors == ()
    assert result.manifest is not None
    assert result.manifest["capture_count"] == 4


def test_reject_unknown_schema_version() -> None:
    data = _golden_package()
    buf = io.BytesIO(data)
    out = io.BytesIO()
    with zipfile.ZipFile(buf, "r") as zin, zipfile.ZipFile(out, "w") as zout:
        for item in zin.infolist():
            content = zin.read(item.filename)
            if item.filename == "manifest.json":
                manifest = json.loads(content.decode("utf-8"))
                manifest["schema_version"] = 999
                content = (json.dumps(manifest, indent=2) + "\n").encode("utf-8")
            zout.writestr(item, content)
    bad = validate_offline_aisle_package_bytes(out.getvalue())
    assert bad.ok is False
    assert any("unsupported_schema_version" in e for e in bad.errors)


def test_detect_hash_mismatch() -> None:
    data = _golden_package()
    buf = io.BytesIO(data)
    out = io.BytesIO()
    with zipfile.ZipFile(buf, "r") as zin, zipfile.ZipFile(out, "w") as zout:
        for item in zin.infolist():
            content = zin.read(item.filename)
            if item.filename == "captures/cap-item.json":
                content = b"{}\n"
            zout.writestr(item, content)
    bad = validate_offline_aisle_package_bytes(out.getvalue())
    assert bad.ok is False
    assert any("hash_mismatch" in e for e in bad.errors)


def test_reject_path_traversal_entry() -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("../../etc/passwd", "x")
        zf.writestr(
            "manifest.json",
            json.dumps(
                {
                    "format": OFFLINE_AISLE_FORMAT,
                    "schema_version": OFFLINE_AISLE_SCHEMA_VERSION,
                    "integrity": {"algorithm": "sha256", "files": {}},
                }
            ),
        )
    result = validate_offline_aisle_package_bytes(buf.getvalue())
    assert result.ok is False
    assert any("path_traversal" in e for e in result.errors)


def test_reject_duplicate_zip_entry() -> None:
    data = _golden_package()
    buf = io.BytesIO(data)
    out = io.BytesIO()
    with zipfile.ZipFile(buf, "r") as zin, zipfile.ZipFile(out, "w") as zout:
        for item in zin.infolist():
            content = zin.read(item.filename)
            zout.writestr(item, content)
            if item.filename == "manifest.json":
                zout.writestr("manifest.json", content)
    result = validate_offline_aisle_package_bytes(out.getvalue())
    assert result.ok is False
    assert any("duplicate_entry:manifest.json" in e for e in result.errors)


def test_reject_unhashed_capture() -> None:
    data = _golden_package()
    buf = io.BytesIO(data)
    out = io.BytesIO()
    with zipfile.ZipFile(buf, "r") as zin, zipfile.ZipFile(out, "w") as zout:
        extra = json.dumps({"capture_id": "extra"}, indent=2) + "\n"
        for item in zin.infolist():
            zout.writestr(item, zin.read(item.filename))
        zout.writestr("captures/extra-unhashed.json", extra)
    result = validate_offline_aisle_package_bytes(out.getvalue())
    assert result.ok is False
    assert any("unexpected_entry" in e or "capture_count_mismatch" in e for e in result.errors)


def test_reject_missing_aisle_json() -> None:
    data = _golden_package()
    buf = io.BytesIO(data)
    out = io.BytesIO()
    with zipfile.ZipFile(buf, "r") as zin, zipfile.ZipFile(out, "w") as zout:
        for item in zin.infolist():
            if item.filename == "aisle.json":
                continue
            zout.writestr(item, zin.read(item.filename))
    result = validate_offline_aisle_package_bytes(out.getvalue())
    assert result.ok is False
    assert any("missing_required:aisle.json" in e for e in result.errors)


def test_reject_missing_profiles_json() -> None:
    data = _golden_package()
    buf = io.BytesIO(data)
    out = io.BytesIO()
    with zipfile.ZipFile(buf, "r") as zin, zipfile.ZipFile(out, "w") as zout:
        for item in zin.infolist():
            if item.filename == "recognition/profiles.json":
                continue
            zout.writestr(item, zin.read(item.filename))
    result = validate_offline_aisle_package_bytes(out.getvalue())
    assert result.ok is False
    assert any("missing_required:recognition/profiles.json" in e for e in result.errors)


def test_capture_count_mismatch() -> None:
    data = _golden_package()
    buf = io.BytesIO(data)
    out = io.BytesIO()
    with zipfile.ZipFile(buf, "r") as zin, zipfile.ZipFile(out, "w") as zout:
        for item in zin.infolist():
            content = zin.read(item.filename)
            if item.filename == "manifest.json":
                manifest = json.loads(content.decode("utf-8"))
                manifest["capture_count"] = 99
                content = (json.dumps(manifest, indent=2) + "\n").encode("utf-8")
            zout.writestr(item, content)
    result = validate_offline_aisle_package_bytes(out.getvalue())
    assert result.ok is False
    assert any("capture_count_mismatch" in e for e in result.errors)


def test_asset_count_mismatch() -> None:
    data = _golden_package()
    buf = io.BytesIO(data)
    out = io.BytesIO()
    with zipfile.ZipFile(buf, "r") as zin, zipfile.ZipFile(out, "w") as zout:
        for item in zin.infolist():
            content = zin.read(item.filename)
            if item.filename == "manifest.json":
                manifest = json.loads(content.decode("utf-8"))
                manifest["asset_count"] = 5
                content = (json.dumps(manifest, indent=2) + "\n").encode("utf-8")
            zout.writestr(item, content)
    result = validate_offline_aisle_package_bytes(out.getvalue())
    assert result.ok is False
    assert any("asset_count_mismatch" in e for e in result.errors)


def test_unexpected_entry() -> None:
    data = _golden_package()
    buf = io.BytesIO(data)
    out = io.BytesIO()
    with zipfile.ZipFile(buf, "r") as zin, zipfile.ZipFile(out, "w") as zout:
        for item in zin.infolist():
            zout.writestr(item, zin.read(item.filename))
        zout.writestr("evil/extra.txt", "x")
    result = validate_offline_aisle_package_bytes(out.getvalue())
    assert result.ok is False
    assert any("unexpected_entry:evil/extra.txt" in e for e in result.errors)


def test_raw_hash_mismatch() -> None:
    data = _golden_package()
    buf = io.BytesIO(data)
    out = io.BytesIO()
    with zipfile.ZipFile(buf, "r") as zin, zipfile.ZipFile(out, "w") as zout:
        for item in zin.infolist():
            content = zin.read(item.filename)
            if item.filename == "captures/cap-item.json":
                cap = json.loads(content.decode("utf-8"))
                cap["recognitions"]["item"]["raw_evidence"]["raw_payload_sha256"] = "deadbeef"
                content = (json.dumps(cap, indent=2) + "\n").encode("utf-8")
            zout.writestr(item, content)
    result = validate_offline_aisle_package_bytes(out.getvalue())
    assert result.ok is False
    assert any("raw_hash_mismatch" in e for e in result.errors)


def test_raw_used_as_sku_guard() -> None:
    data = _golden_package()
    buf = io.BytesIO(data)
    out = io.BytesIO()
    with zipfile.ZipFile(buf, "r") as zin, zipfile.ZipFile(out, "w") as zout:
        for item in zin.infolist():
            content = zin.read(item.filename)
            if item.filename == "captures/cap-item.json":
                cap = json.loads(content.decode("utf-8"))
                raw = cap["recognitions"]["item"]["raw_evidence"]["raw_payload"]
                cap["result"]["product"]["sku"] = raw
                content = (json.dumps(cap, indent=2) + "\n").encode("utf-8")
            zout.writestr(item, content)
    result = validate_offline_aisle_package_bytes(out.getvalue())
    assert result.ok is False
    assert any("raw_used_as_sku" in e for e in result.errors)


def test_product_with_position_contract_accepted() -> None:
    result = validate_offline_aisle_package_bytes(_golden_package())
    assert result.ok is True
