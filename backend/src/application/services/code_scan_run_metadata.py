"""Stable metadata_json helpers for aisle code scan runs."""

from __future__ import annotations

from typing import Any


def empty_run_metadata() -> dict[str, Any]:
    return {
        "warnings": [],
        "skipped_assets": [],
        "scanner_errors": [],
        "unreadable_assets": [],
        "unsupported_assets": [],
    }


def build_run_metadata(
    *,
    warnings: list[str] | None = None,
    skipped_assets: list[Any] | None = None,
    scanner_errors: list[str] | None = None,
    unreadable_assets: list[dict[str, Any]] | None = None,
    unsupported_assets: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build run metadata with stable keys."""
    return {
        "warnings": list(warnings or []),
        "skipped_assets": list(skipped_assets or []),
        "scanner_errors": list(scanner_errors or []),
        "unreadable_assets": list(unreadable_assets or []),
        "unsupported_assets": list(unsupported_assets or []),
    }


def skipped_asset_entry(
    *,
    asset_id: str,
    reason: str,
    asset_type: str | None = None,
) -> dict[str, Any]:
    entry: dict[str, Any] = {"asset_id": asset_id, "reason": reason}
    if asset_type is not None:
        entry["asset_type"] = asset_type
    return entry


def _as_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(x) for x in value]


def _as_asset_entry_list(
    value: Any,
    *,
    legacy_reason: str | None = None,
) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    out: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, dict):
            asset_id = item.get("asset_id")
            reason = item.get("reason")
            if asset_id is not None and reason is not None:
                entry: dict[str, Any] = {
                    "asset_id": str(asset_id),
                    "reason": str(reason),
                }
                if item.get("asset_type") is not None:
                    entry["asset_type"] = str(item["asset_type"])
                out.append(entry)
        elif legacy_reason and isinstance(item, str) and item.strip():
            out.append({"asset_id": item.strip(), "reason": legacy_reason})
    return out


def parse_run_metadata(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Normalize persisted metadata to the stable shape."""
    if not raw:
        return empty_run_metadata()
    return {
        "warnings": _as_str_list(raw.get("warnings")),
        "scanner_errors": _as_str_list(raw.get("scanner_errors")),
        "skipped_assets": _as_asset_entry_list(
            raw.get("skipped_assets"), legacy_reason="legacy_skipped"
        ),
        "unreadable_assets": _as_asset_entry_list(raw.get("unreadable_assets")),
        "unsupported_assets": _as_asset_entry_list(raw.get("unsupported_assets")),
    }


def warnings_from_run_metadata(raw: dict[str, Any] | None) -> list[str]:
    return parse_run_metadata(raw)["warnings"]
