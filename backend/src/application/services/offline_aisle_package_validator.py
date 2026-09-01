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

MAX_FILES = 10_000
MAX_UNCOMPRESSED_BYTES = 512 * 1024 * 1024
MAX_SINGLE_FILE_BYTES = 32 * 1024 * 1024
MAX_COMPRESSION_RATIO = 200

ALLOWED_ASSET_EXTENSIONS = frozenset(
    {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif", ".gif", ".bmp"}
)

REQUIRED_ROOT_FILES = frozenset(
    {"manifest.json", "aisle.json", "recognition/profiles.json"}
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


def _is_allowed_v1_path(name: str) -> bool:
    normalized = name.replace("\\", "/")
    if normalized in REQUIRED_ROOT_FILES:
        return True
    if normalized.startswith("captures/") and normalized.endswith(".json"):
        return True
    if normalized.startswith("assets/"):
        dot = normalized.rfind(".")
        if dot < 0:
            return False
        ext = normalized[dot:].lower()
        return ext in ALLOWED_ASSET_EXTENSIONS
    return False


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


def _expected_integrity_paths(names: list[str], captures: list[dict[str, Any]]) -> set[str]:
    expected = {"aisle.json", "recognition/profiles.json"}
    for name in names:
        if name.startswith("captures/") and name.endswith(".json"):
            expected.add(name)
    for cap in captures:
        asset = cap.get("asset") or {}
        if asset.get("included") and asset.get("path"):
            expected.add(str(asset["path"]))
    return expected


def validate_offline_aisle_package_bytes(data: bytes) -> OfflineAislePackageValidationResult:
    errors: list[str] = []
    manifest: dict[str, Any] | None = None
    try:
        with zipfile.ZipFile(io.BytesIO(data), "r") as zf:
            names = zf.namelist()
            if len(names) > MAX_FILES:
                errors.append(f"too_many_files:{len(names)}")
                return OfflineAislePackageValidationResult(False, tuple(errors), None)

            name_counts = Counter(names)
            for entry_name, count in name_counts.items():
                if count > 1:
                    errors.append(f"duplicate_entry:{entry_name}")

            for name in names:
                if not _safe_entry_name(name):
                    errors.append(f"path_traversal:{name}")
                if not _is_allowed_v1_path(name):
                    errors.append(f"unexpected_entry:{name}")

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

            for required in REQUIRED_ROOT_FILES:
                if required not in names:
                    errors.append(f"missing_required:{required}")

            if "manifest.json" not in names:
                return OfflineAislePackageValidationResult(False, tuple(errors), None)

            manifest_raw = zf.read("manifest.json")
            manifest = json.loads(manifest_raw.decode("utf-8"))
            if manifest.get("format") != OFFLINE_AISLE_FORMAT:
                errors.append("invalid_format")
            schema_version = manifest.get("schema_version")
            if schema_version != OFFLINE_AISLE_SCHEMA_VERSION:
                errors.append(f"unsupported_schema_version:{schema_version}")

            integrity = manifest.get("integrity") or {}
            files_hashes: dict[str, str] = integrity.get("files") or {}
            if integrity.get("algorithm") != "sha256":
                errors.append("invalid_integrity_algorithm")

            capture_paths = sorted(
                n for n in names if n.startswith("captures/") and n.endswith(".json")
            )
            capture_count_manifest = manifest.get("capture_count")
            if (
                isinstance(capture_count_manifest, int)
                and capture_count_manifest != len(capture_paths)
            ):
                errors.append(
                    f"capture_count_mismatch:manifest={capture_count_manifest}:actual={len(capture_paths)}"
                )

            captures: list[dict[str, Any]] = []
            aisle_id = (manifest.get("aisle") or {}).get("id")
            capture_ids: set[str] = set()
            included_asset_count = 0

            for cap_path in capture_paths:
                cap = json.loads(zf.read(cap_path).decode("utf-8"))
                captures.append(cap)
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

            asset_count_manifest = manifest.get("asset_count")
            if (
                isinstance(asset_count_manifest, int)
                and asset_count_manifest != included_asset_count
            ):
                errors.append(
                    f"asset_count_mismatch:manifest={asset_count_manifest}:actual={included_asset_count}"
                )

            expected_paths = _expected_integrity_paths(names, captures)
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

    except zipfile.BadZipFile:
        errors.append("bad_zip")
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        errors.append(f"parse_error:{exc}")

    return OfflineAislePackageValidationResult(len(errors) == 0, tuple(errors), manifest)
