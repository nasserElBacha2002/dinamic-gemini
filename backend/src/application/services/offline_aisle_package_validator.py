"""Read-only validator for DINAMIC_OFFLINE_AISLE portable packages (Phase 4 preparatory)."""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from collections import Counter
from dataclasses import dataclass
from typing import Any

OFFLINE_AISLE_FORMAT = "DINAMIC_OFFLINE_AISLE"
OFFLINE_AISLE_SCHEMA_VERSION = 1
OFFLINE_AISLE_SCHEMA_VERSION_V2 = 2
SUPPORTED_SCHEMA_VERSIONS = frozenset({OFFLINE_AISLE_SCHEMA_VERSION, OFFLINE_AISLE_SCHEMA_VERSION_V2})
AISLE_PACKAGE_PAYLOAD_PATH = "aisle-package.json"

MAX_FILES = 10_000
MAX_UNCOMPRESSED_BYTES = 512 * 1024 * 1024
MAX_SINGLE_FILE_BYTES = 32 * 1024 * 1024
MAX_COMPRESSION_RATIO = 200

ALLOWED_ASSET_EXTENSIONS = frozenset(
    {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif", ".gif", ".bmp"}
)

REQUIRED_ROOT_FILES_V1 = frozenset(
    {"manifest.json", "aisle.json", "recognition/profiles.json"}
)
REQUIRED_ROOT_FILES_V2 = frozenset({"manifest.json", AISLE_PACKAGE_PAYLOAD_PATH})

VALID_CAPTURE_RESULT_KINDS = frozenset(
    {
        "PRODUCT",
        "POSITION_ONLY",
        "PRODUCT_WITH_POSITION",
        "UNRECOGNIZED",
        "MANUAL_REVIEW",
    }
)


@dataclass(frozen=True)
class OfflineAislePackageValidationResult:
    ok: bool
    errors: tuple[str, ...]
    manifest: dict[str, Any] | None


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_text(text: str) -> str:
    return _sha256_bytes(text.encode("utf-8"))


def _safe_entry_name(name: str) -> bool:
    normalized = name.replace("\\", "/")
    if normalized.startswith("/") or ".." in normalized.split("/"):
        return False
    return True


def _is_allowed_asset_path(name: str) -> bool:
    normalized = name.replace("\\", "/")
    if not normalized.startswith("assets/"):
        return False
    dot = normalized.rfind(".")
    if dot < 0:
        return False
    ext = normalized[dot:].lower()
    return ext in ALLOWED_ASSET_EXTENSIONS


def _is_allowed_v1_path(name: str) -> bool:
    normalized = name.replace("\\", "/")
    if normalized in REQUIRED_ROOT_FILES_V1:
        return True
    if normalized.startswith("captures/") and normalized.endswith(".json"):
        return True
    return _is_allowed_asset_path(name)


def _is_allowed_v2_path(name: str) -> bool:
    normalized = name.replace("\\", "/")
    if normalized in REQUIRED_ROOT_FILES_V2:
        return True
    return _is_allowed_asset_path(name)


def _provenance_raw(cap: dict[str, Any], kind: str) -> tuple[str | None, str | None]:
    recognitions = cap.get("recognitions") or {}
    branch = recognitions.get(kind) or {}
    raw_evidence = branch.get("raw_evidence") or {}
    return raw_evidence.get("raw_payload"), raw_evidence.get("raw_payload_sha256")


def _validate_capture_provenance(
    cap_path: str,
    cap: dict[str, Any],
    errors: list[str],
) -> None:
    for kind in ("item", "position"):
        raw, expected_hash = _provenance_raw(cap, kind)
        if raw and expected_hash:
            actual = _sha256_text(raw)
            if actual != expected_hash:
                errors.append(f"raw_hash_mismatch:{cap_path}:{kind}")
        sku = ((cap.get("result") or {}).get("product") or {}).get("sku")
        if raw and sku == raw:
            errors.append(f"raw_used_as_sku:{cap_path}")


def _validate_profile_refs(
    profiles: list[dict[str, Any]],
    captures: list[dict[str, Any]],
    errors: list[str],
) -> None:
    refs = {
        str(entry["profile_ref"])
        for entry in profiles
        if isinstance(entry, dict) and entry.get("profile_ref")
    }
    for cap in captures:
        cap_id = cap.get("capture_id", "unknown")
        recognitions = cap.get("recognitions") or {}
        for kind in ("item", "position"):
            branch = recognitions.get(kind) or {}
            ref = branch.get("profile_ref")
            if ref and str(ref) not in refs:
                errors.append(f"invalid_profile_ref:{cap_id}:{kind}:{ref}")


def _expected_integrity_paths_v1(names: list[str], captures: list[dict[str, Any]]) -> set[str]:
    expected = {"aisle.json", "recognition/profiles.json"}
    for name in names:
        if name.startswith("captures/") and name.endswith(".json"):
            expected.add(name)
    for cap in captures:
        asset = cap.get("asset") or {}
        if asset.get("included") and asset.get("path"):
            expected.add(str(asset["path"]))
    return expected


def _expected_integrity_paths_v2(captures: list[dict[str, Any]]) -> set[str]:
    expected = {AISLE_PACKAGE_PAYLOAD_PATH}
    for cap in captures:
        asset = cap.get("asset") or {}
        if asset.get("included") and asset.get("path"):
            expected.add(str(asset["path"]))
    return expected


def _validate_captures_common(
    *,
    captures: list[dict[str, Any]],
    aisle_id: str | None,
    cap_path_prefix: str,
    errors: list[str],
) -> int:
    capture_ids: set[str] = set()
    included_asset_count = 0
    for index, cap in enumerate(captures):
        cap_path = f"{cap_path_prefix}[{index}]"
        cap_id = cap.get("capture_id")
        if isinstance(cap_id, str):
            if cap_id in capture_ids:
                errors.append(f"duplicate_capture_id:{cap_id}")
            capture_ids.add(cap_id)
        if aisle_id and cap.get("aisle_id") != aisle_id:
            errors.append(f"capture_aisle_mismatch:{cap_path}")
        asset = cap.get("asset") or {}
        if asset.get("included"):
            included_asset_count += 1
        _validate_capture_provenance(cap_path, cap, errors)
    return included_asset_count


def _validate_zip_envelope(zf: zipfile.ZipFile, errors: list[str]) -> list[str]:
    names = zf.namelist()
    if len(names) > MAX_FILES:
        errors.append(f"too_many_files:{len(names)}")
        return names

    name_counts = Counter(names)
    for entry_name, count in name_counts.items():
        if count > 1:
            errors.append(f"duplicate_entry:{entry_name}")

    total = 0
    for info in zf.infolist():
        if info.file_size > MAX_SINGLE_FILE_BYTES:
            errors.append(f"file_too_large:{info.filename}")
        total += info.file_size
        if info.compress_size > 0 and info.file_size > 0:
            ratio = info.file_size / info.compress_size
            if ratio > MAX_COMPRESSION_RATIO:
                errors.append(f"compression_ratio_exceeded:{info.filename}")
    if total > MAX_UNCOMPRESSED_BYTES:
        errors.append(f"uncompressed_too_large:{total}")
    return names


def _non_empty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _validate_v2_payload_aisle(aisle: dict[str, Any], errors: list[str]) -> None:
    if not _non_empty_str(aisle.get("id")):
        errors.append("invalid_payload_aisle_id")
    if not _non_empty_str(aisle.get("inventory_id")):
        errors.append("invalid_payload_aisle_inventory_id")


def _validate_v2_capture_structure(cap: dict[str, Any], cap_path: str, errors: list[str]) -> bool:
    structurally_valid = True
    if not _non_empty_str(cap.get("capture_id")):
        errors.append(f"invalid_capture_structure:{cap_path}:capture_id")
        structurally_valid = False
    if not _non_empty_str(cap.get("capture_session_id")):
        errors.append(f"invalid_capture_structure:{cap_path}:capture_session_id")
        structurally_valid = False
    if not _non_empty_str(cap.get("aisle_id")):
        errors.append(f"invalid_capture_structure:{cap_path}:aisle_id")
        structurally_valid = False
    result_kind = cap.get("result_kind")
    if not isinstance(result_kind, str) or result_kind not in VALID_CAPTURE_RESULT_KINDS:
        errors.append(f"invalid_capture_structure:{cap_path}:result_kind")
        structurally_valid = False
    if not isinstance(cap.get("recognitions"), dict):
        errors.append(f"invalid_capture_structure:{cap_path}:recognitions")
        structurally_valid = False
    result = cap.get("result")
    if not isinstance(result, dict):
        errors.append(f"invalid_capture_structure:{cap_path}:result")
        structurally_valid = False
    if "asset" not in cap:
        errors.append(f"invalid_capture_structure:{cap_path}:asset")
        structurally_valid = False
    else:
        asset = cap.get("asset")
        if asset is not None and not isinstance(asset, dict):
            errors.append(f"invalid_capture_structure:{cap_path}:asset")
            structurally_valid = False
    return structurally_valid


def _validate_capture_asset_declared_hashes(
    captures: list[dict[str, Any]],
    files_hashes: dict[str, str],
    errors: list[str],
) -> None:
    for cap in captures:
        asset = cap.get("asset")
        if not isinstance(asset, dict) or not asset.get("included"):
            continue
        cap_id = cap.get("capture_id")
        cap_label = cap_id if isinstance(cap_id, str) and cap_id else "unknown"
        path = asset.get("path")
        if not isinstance(path, str) or not path.strip() or not _is_allowed_asset_path(path):
            errors.append(f"invalid_asset_path:{cap_label}")
            continue
        declared = asset.get("sha256")
        if not isinstance(declared, str) or not declared.strip():
            errors.append(f"missing_asset_sha256:{cap_label}")
            continue
        manifest_hash = files_hashes.get(path)
        if manifest_hash is None:
            errors.append(f"missing_integrity_path:{path}")
            continue
        if declared != manifest_hash:
            errors.append(f"capture_asset_sha256_mismatch:{cap_label}:{path}")


def _validate_integrity_hashes(
    zf: zipfile.ZipFile,
    names: list[str],
    files_hashes: dict[str, str],
    expected_paths: set[str],
    errors: list[str],
) -> None:
    integrity_paths = set(files_hashes.keys())
    if integrity_paths != expected_paths:
        missing = expected_paths - integrity_paths
        extra = integrity_paths - expected_paths
        for path in sorted(missing):
            errors.append(f"missing_integrity_path:{path}")
        for path in sorted(extra):
            errors.append(f"unexpected_integrity_path:{path}")

    for path, expected in files_hashes.items():
        if path not in names:
            errors.append(f"missing_integrity_file:{path}")
            continue
        actual = _sha256_bytes(zf.read(path))
        if actual != expected:
            errors.append(f"hash_mismatch:{path}")


def _validate_offline_aisle_package_v1(
    zf: zipfile.ZipFile,
    names: list[str],
    manifest: dict[str, Any],
    errors: list[str],
) -> None:
    for name in names:
        if not _is_allowed_v1_path(name):
            errors.append(f"unexpected_entry:{name}")

    for required in REQUIRED_ROOT_FILES_V1:
        if required not in names:
            errors.append(f"missing_required:{required}")

    integrity = manifest.get("integrity") or {}
    files_hashes: dict[str, str] = integrity.get("files") or {}
    if integrity.get("algorithm") != "sha256":
        errors.append("invalid_integrity_algorithm")

    capture_paths = sorted(n for n in names if n.startswith("captures/") and n.endswith(".json"))
    capture_count_manifest = manifest.get("capture_count")
    if isinstance(capture_count_manifest, int) and capture_count_manifest != len(capture_paths):
        errors.append(
            f"capture_count_mismatch:manifest={capture_count_manifest}:actual={len(capture_paths)}"
        )

    captures: list[dict[str, Any]] = []
    aisle_id = (manifest.get("aisle") or {}).get("id")
    for cap_path in capture_paths:
        cap = json.loads(zf.read(cap_path).decode("utf-8"))
        captures.append(cap)

    included_asset_count = _validate_captures_common(
        captures=captures,
        aisle_id=aisle_id if isinstance(aisle_id, str) else None,
        cap_path_prefix="captures",
        errors=errors,
    )

    asset_count_manifest = manifest.get("asset_count")
    if isinstance(asset_count_manifest, int) and asset_count_manifest != included_asset_count:
        errors.append(
            f"asset_count_mismatch:manifest={asset_count_manifest}:actual={included_asset_count}"
        )

    expected_paths = _expected_integrity_paths_v1(names, captures)
    _validate_integrity_hashes(zf, names, files_hashes, expected_paths, errors)


def _parse_payload_v2(raw: bytes, errors: list[str]) -> dict[str, Any] | None:
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        errors.append(f"payload_parse_error:{exc}")
        return None
    if not isinstance(payload, dict):
        errors.append("invalid_payload_structure")
        return None
    for key in ("aisle", "profiles", "captures"):
        if key not in payload:
            errors.append(f"missing_payload_field:{key}")
    aisle = payload.get("aisle")
    profiles = payload.get("profiles")
    captures = payload.get("captures")
    if aisle is not None and not isinstance(aisle, dict):
        errors.append("invalid_payload_aisle")
    if profiles is not None and not isinstance(profiles, list):
        errors.append("invalid_payload_profiles")
    if captures is not None and not isinstance(captures, list):
        errors.append("invalid_payload_captures")
    return payload if isinstance(payload, dict) else None


def _validate_offline_aisle_package_v2(
    zf: zipfile.ZipFile,
    names: list[str],
    manifest: dict[str, Any],
    errors: list[str],
) -> None:
    for name in names:
        if not _is_allowed_v2_path(name):
            errors.append(f"unexpected_entry:{name}")

    payload_present = AISLE_PACKAGE_PAYLOAD_PATH in names
    for required in REQUIRED_ROOT_FILES_V2:
        if required not in names:
            errors.append(f"missing_required:{required}")

    if not payload_present:
        return

    integrity = manifest.get("integrity") or {}
    files_hashes: dict[str, str] = integrity.get("files") or {}
    if integrity.get("algorithm") != "sha256":
        errors.append("invalid_integrity_algorithm")

    payload_raw = zf.read(AISLE_PACKAGE_PAYLOAD_PATH)
    payload = _parse_payload_v2(payload_raw, errors)
    if payload is None:
        return

    aisle_doc = payload.get("aisle") if isinstance(payload.get("aisle"), dict) else {}
    _validate_v2_payload_aisle(aisle_doc, errors)

    captures_raw = payload.get("captures")
    captures: list[dict[str, Any]] = []
    semantically_valid_captures: list[dict[str, Any]] = []
    if isinstance(captures_raw, list):
        for index, entry in enumerate(captures_raw):
            cap_path = f"{AISLE_PACKAGE_PAYLOAD_PATH}:captures[{index}]"
            if isinstance(entry, dict):
                captures.append(entry)
                if _validate_v2_capture_structure(entry, cap_path, errors):
                    semantically_valid_captures.append(entry)
            else:
                errors.append("invalid_capture_entry")

    capture_count_manifest = manifest.get("capture_count")
    if isinstance(capture_count_manifest, int) and capture_count_manifest != len(captures):
        errors.append(
            f"capture_count_mismatch:manifest={capture_count_manifest}:actual={len(captures)}"
        )

    aisle_id = aisle_doc.get("id")
    manifest_aisle_id = (manifest.get("aisle") or {}).get("id")
    if (
        isinstance(aisle_id, str)
        and isinstance(manifest_aisle_id, str)
        and aisle_id != manifest_aisle_id
    ):
        errors.append("payload_aisle_manifest_mismatch")

    profiles_raw = payload.get("profiles")
    profiles: list[dict[str, Any]] = []
    if isinstance(profiles_raw, list):
        for entry in profiles_raw:
            if isinstance(entry, dict):
                profiles.append(entry)
            else:
                errors.append("invalid_profile_entry")

    included_asset_count = _validate_captures_common(
        captures=semantically_valid_captures,
        aisle_id=aisle_id if isinstance(aisle_id, str) else None,
        cap_path_prefix=AISLE_PACKAGE_PAYLOAD_PATH,
        errors=errors,
    )
    _validate_profile_refs(profiles, semantically_valid_captures, errors)

    asset_count_manifest = manifest.get("asset_count")
    if isinstance(asset_count_manifest, int) and asset_count_manifest != included_asset_count:
        errors.append(
            f"asset_count_mismatch:manifest={asset_count_manifest}:actual={included_asset_count}"
        )

    expected_paths = _expected_integrity_paths_v2(semantically_valid_captures)
    _validate_capture_asset_declared_hashes(semantically_valid_captures, files_hashes, errors)
    _validate_integrity_hashes(zf, names, files_hashes, expected_paths, errors)


def validate_offline_aisle_package_bytes(data: bytes) -> OfflineAislePackageValidationResult:
    errors: list[str] = []
    manifest: dict[str, Any] | None = None
    try:
        with zipfile.ZipFile(io.BytesIO(data), "r") as zf:
            names = _validate_zip_envelope(zf, errors)
            if errors and any(e.startswith("too_many_files:") for e in errors):
                return OfflineAislePackageValidationResult(False, tuple(errors), None)

            for name in names:
                if not _safe_entry_name(name):
                    errors.append(f"path_traversal:{name}")

            if "manifest.json" not in names:
                return OfflineAislePackageValidationResult(False, tuple(errors), None)

            manifest_raw = zf.read("manifest.json")
            manifest = json.loads(manifest_raw.decode("utf-8"))
            if manifest.get("format") != OFFLINE_AISLE_FORMAT:
                errors.append("invalid_format")
            schema_version = manifest.get("schema_version")
            if schema_version not in SUPPORTED_SCHEMA_VERSIONS:
                errors.append(f"unsupported_schema_version:{schema_version}")
            elif schema_version == OFFLINE_AISLE_SCHEMA_VERSION:
                _validate_offline_aisle_package_v1(zf, names, manifest, errors)
            elif schema_version == OFFLINE_AISLE_SCHEMA_VERSION_V2:
                _validate_offline_aisle_package_v2(zf, names, manifest, errors)

    except zipfile.BadZipFile:
        errors.append("bad_zip")
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        errors.append(f"parse_error:{exc}")

    return OfflineAislePackageValidationResult(len(errors) == 0, tuple(errors), manifest)
