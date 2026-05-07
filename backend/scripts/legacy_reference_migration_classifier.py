# READ ONLY — NO DATA MODIFICATION
"""Pure classification logic for legacy ``inventory_visual_references`` → supplier migration dry-run (C5).

No database or filesystem access in this module. Safe for unit tests without SQL Server.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

# Align with supplier reference image MIME allow-list (subset check for invalid MIME).
_ALLOWED_MIME = frozenset(
    {
        "image/jpeg",
        "image/jpg",
        "image/png",
        "image/webp",
    }
)


class MigrationCategory(str, Enum):
    AUTO_SINGLE_SUPPLIER = "AUTO_SINGLE_SUPPLIER"
    AUTO_LEGACY_DEFAULT_SUPPLIER = "AUTO_LEGACY_DEFAULT_SUPPLIER"
    AMBIGUOUS_MULTI_SUPPLIER = "AMBIGUOUS_MULTI_SUPPLIER"
    AMBIGUOUS_MISSING_CLIENT = "AMBIGUOUS_MISSING_CLIENT"
    AMBIGUOUS_NO_SUPPLIER = "AMBIGUOUS_NO_SUPPLIER"
    SKIP_ALREADY_MIGRATED = "SKIP_ALREADY_MIGRATED"
    SKIP_MISSING_STORAGE = "SKIP_MISSING_STORAGE"
    SKIP_INVALID_ROW = "SKIP_INVALID_ROW"


@dataclass(frozen=True)
class InventoryDryRunSummary:
    """Aggregated aisle/supplier linkage for one inventory."""

    inventory_id: str
    client_id: str | None
    distinct_aisle_supplier_ids: frozenset[str]


@dataclass
class ClassificationDetail:
    reference_id: str
    inventory_id: str
    category: MigrationCategory
    reason_code: str = ""
    target_client_id: str | None = None
    target_client_supplier_id: str | None = None
    duplicate_candidate: bool = False
    local_file_missing: bool | None = None
    extra: dict[str, Any] = field(default_factory=dict)


def normalize_mime(mime_type: str) -> str:
    raw = (mime_type or "").strip().lower()
    return "image/jpeg" if raw == "image/jpg" else raw


def storage_metadata_sufficient(*, row: dict[str, Any]) -> tuple[bool, str]:
    """Return whether migration can address blob location (provider-complete OR legacy path)."""

    prov = (row.get("storage_provider") or "").strip().lower()
    key = (row.get("storage_key") or "").strip()
    bucket = (row.get("storage_bucket") or "").strip()
    path = (row.get("storage_path") or "").strip()

    has_any_provider_field = bool(prov or key or bucket)
    if has_any_provider_field:
        if not prov:
            return False, "partial_provider_missing_provider"
        if prov == "s3":
            if not bucket or not key:
                return False, "partial_provider_s3_incomplete"
            return True, "provider_s3"
        if prov == "local":
            if key:
                return True, "provider_local_key"
            if path:
                return True, "provider_local_path_fallback"
            return False, "partial_provider_local_no_key_no_path"
        return False, f"unsupported_provider:{prov}"

    if path:
        return True, "legacy_path_only"
    return False, "no_path_no_provider"


def already_migrated_heuristic(
    *,
    target_supplier_id: str,
    legacy_storage_path: str,
    legacy_storage_key: str,
    migrated_pairs_paths: frozenset[tuple[str, str]],
    migrated_pairs_keys: frozenset[tuple[str, str]],
) -> bool:
    """Detect overlap with existing ``supplier_reference_images`` rows (best-effort, no mapping table)."""

    p = legacy_storage_path.strip()
    k = legacy_storage_key.strip()
    if k and (target_supplier_id, k) in migrated_pairs_keys:
        return True
    if p and (target_supplier_id, p) in migrated_pairs_paths:
        return True
    return False


def duplicate_upload_candidate(
    *,
    target_supplier_id: str,
    filename: str,
    existing_filenames_by_supplier: dict[str, frozenset[str]],
) -> bool:
    names = existing_filenames_by_supplier.get(target_supplier_id, frozenset())
    return filename.strip() in names


def classify_legacy_reference_row(
    *,
    row: dict[str, Any],
    inventory_missing: bool,
    inventory_summary: InventoryDryRunSummary | None,
    legacy_default_supplier_by_client: dict[str, str],
    accept_default_supplier_fallback: bool,
    migrated_pairs_paths: frozenset[tuple[str, str]],
    migrated_pairs_keys: frozenset[tuple[str, str]],
    existing_filenames_by_supplier: dict[str, frozenset[str]],
    supplier_client_map: dict[str, str],
) -> ClassificationDetail:
    reference_id = str(row.get("id") or "").strip()
    inventory_id = str(row.get("inventory_id") or "").strip()
    filename = str(row.get("filename") or "").strip()
    mime_raw = str(row.get("mime_type") or "")
    mime = normalize_mime(mime_raw)
    file_size_raw = row.get("file_size")
    storage_path = str(row.get("storage_path") or "").strip()
    storage_key = str(row.get("storage_key") or "").strip()

    detail = ClassificationDetail(
        reference_id=reference_id or "?",
        inventory_id=inventory_id or "?",
        category=MigrationCategory.SKIP_INVALID_ROW,
        reason_code="",
    )

    if not reference_id or not inventory_id:
        detail.reason_code = "missing_primary_keys"
        return detail

    if inventory_missing or inventory_summary is None:
        detail.reason_code = "orphan_inventory_fk_or_missing_join"
        return detail

    if not filename:
        detail.reason_code = "missing_filename"
        return detail

    try:
        file_size = int(file_size_raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        detail.reason_code = "invalid_file_size"
        return detail

    if file_size <= 0:
        detail.reason_code = "non_positive_file_size"
        return detail

    if mime not in _ALLOWED_MIME:
        detail.reason_code = "unsupported_mime_type"
        detail.extra["mime_type"] = mime_raw
        return detail

    storage_ok, storage_reason = storage_metadata_sufficient(row=row)
    if not storage_ok:
        detail.category = MigrationCategory.SKIP_MISSING_STORAGE
        detail.reason_code = storage_reason
        return detail

    client_id = inventory_summary.client_id
    suppliers = inventory_summary.distinct_aisle_supplier_ids

    if client_id is None or not str(client_id).strip():
        detail.category = MigrationCategory.AMBIGUOUS_MISSING_CLIENT
        detail.reason_code = "inventory_client_id_null"
        return detail

    client_id_s = str(client_id).strip()

    if len(suppliers) > 1:
        detail.category = MigrationCategory.AMBIGUOUS_MULTI_SUPPLIER
        detail.reason_code = "multiple_distinct_aisle_suppliers"
        detail.extra["distinct_supplier_ids"] = sorted(suppliers)
        detail.target_client_id = client_id_s
        return detail

    target_supplier_id: str | None = None
    category_after_resolution = MigrationCategory.AMBIGUOUS_NO_SUPPLIER

    if len(suppliers) == 1:
        only = next(iter(suppliers))
        detail.extra["resolved_single_supplier_id"] = only
        ok_supplier, bad_reason = validate_single_supplier_belongs_to_client(
            supplier_id=only,
            inventory_client_id=client_id_s,
            supplier_client_map=supplier_client_map,
        )
        if not ok_supplier:
            detail.category = MigrationCategory.SKIP_INVALID_ROW
            detail.reason_code = bad_reason
            detail.target_client_id = client_id_s
            detail.extra["expected_inventory_client_id"] = client_id_s
            return detail

        detail.target_client_id = client_id_s
        detail.target_client_supplier_id = only
        category_after_resolution = MigrationCategory.AUTO_SINGLE_SUPPLIER
        target_supplier_id = only
    elif len(suppliers) == 0:
        detail.target_client_id = client_id_s
        default_sid = legacy_default_supplier_by_client.get(client_id_s)
        if default_sid:
            if supplier_client_map.get(default_sid) != client_id_s:
                detail.reason_code = "legacy_default_supplier_wrong_client_data_bug"
                detail.category = MigrationCategory.SKIP_INVALID_ROW
                detail.target_client_id = client_id_s
                return detail

            if accept_default_supplier_fallback:
                detail.target_client_supplier_id = default_sid
                category_after_resolution = MigrationCategory.AUTO_LEGACY_DEFAULT_SUPPLIER
                target_supplier_id = default_sid
                detail.reason_code = "no_aisle_supplier_using_legacy_default_supplier"
            else:
                detail.category = MigrationCategory.AMBIGUOUS_NO_SUPPLIER
                detail.reason_code = "no_aisle_supplier_fallback_disabled"
                return detail
        else:
            detail.category = MigrationCategory.AMBIGUOUS_NO_SUPPLIER
            detail.reason_code = "no_aisle_supplier_no_legacy_default_row"
            return detail

    assert target_supplier_id is not None

    if already_migrated_heuristic(
        target_supplier_id=target_supplier_id,
        legacy_storage_path=storage_path,
        legacy_storage_key=storage_key,
        migrated_pairs_paths=migrated_pairs_paths,
        migrated_pairs_keys=migrated_pairs_keys,
    ):
        detail.category = MigrationCategory.SKIP_ALREADY_MIGRATED
        detail.reason_code = "heuristic_storage_match_existing_supplier_row"
        detail.target_client_supplier_id = target_supplier_id
        detail.target_client_id = client_id_s
        detail.extra["storage_classification"] = storage_reason
        return detail

    detail.category = category_after_resolution
    detail.target_client_id = client_id_s
    detail.target_client_supplier_id = target_supplier_id
    if detail.category == MigrationCategory.AUTO_SINGLE_SUPPLIER:
        detail.reason_code = "single_distinct_aisle_supplier"
    elif detail.category == MigrationCategory.AUTO_LEGACY_DEFAULT_SUPPLIER:
        detail.reason_code = detail.reason_code or "legacy_default_supplier_fallback"
    detail.extra["storage_classification"] = storage_reason

    detail.duplicate_candidate = duplicate_upload_candidate(
        target_supplier_id=target_supplier_id,
        filename=filename,
        existing_filenames_by_supplier=existing_filenames_by_supplier,
    )

    return detail


def validate_single_supplier_belongs_to_client(
    *,
    supplier_id: str,
    inventory_client_id: str,
    supplier_client_map: dict[str, str],
) -> tuple[bool, str]:
    """Return (ok, reason). Used by analyzer after SQL join verification."""

    actual = supplier_client_map.get(supplier_id)
    if actual is None:
        return False, "supplier_not_found"
    if actual.strip() != inventory_client_id.strip():
        return False, "supplier_client_mismatch"
    return True, ""
