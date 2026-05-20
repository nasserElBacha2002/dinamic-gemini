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


def parse_run_metadata(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Normalize persisted metadata to the stable shape."""
    if not raw:
        return empty_run_metadata()
    base = empty_run_metadata()
    for key in base:
        val = raw.get(key)
        if key == "skipped_assets":
            if isinstance(val, list):
                base[key] = val
            continue
        if isinstance(val, list):
            base[key] = [str(x) if key != "unreadable_assets" and key != "unsupported_assets" else x for x in val]
        elif key in ("unreadable_assets", "unsupported_assets") and isinstance(val, list):
            base[key] = val
    if isinstance(raw.get("warnings"), list):
        base["warnings"] = [str(w) for w in raw["warnings"]]
    if isinstance(raw.get("scanner_errors"), list):
        base["scanner_errors"] = [str(e) for e in raw["scanner_errors"]]
    skipped = raw.get("skipped_assets")
    if isinstance(skipped, list):
        base["skipped_assets"] = skipped
    for structured in ("unreadable_assets", "unsupported_assets"):
        val = raw.get(structured)
        if isinstance(val, list):
            base[structured] = [x for x in val if isinstance(x, dict)]
    return base


def warnings_from_run_metadata(raw: dict[str, Any] | None) -> list[str]:
    return parse_run_metadata(raw)["warnings"]
