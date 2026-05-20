"""Stable metadata_json helpers for aisle code scan runs."""

from __future__ import annotations

from typing import Any


def empty_run_metadata() -> dict[str, Any]:
    return {
        "warnings": [],
        "skipped_assets": [],
        "scanner_errors": [],
    }


def build_run_metadata(
    *,
    warnings: list[str] | None = None,
    skipped_assets: list[str] | None = None,
    scanner_errors: list[str] | None = None,
) -> dict[str, Any]:
    """Build run metadata with stable keys (backward compatible with legacy ``warnings``-only blobs)."""
    return {
        "warnings": list(warnings or []),
        "skipped_assets": list(skipped_assets or []),
        "scanner_errors": list(scanner_errors or []),
    }


def parse_run_metadata(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Normalize persisted metadata to the stable shape."""
    if not raw:
        return empty_run_metadata()
    warnings = raw.get("warnings")
    skipped = raw.get("skipped_assets")
    scanner_errors = raw.get("scanner_errors")
    return {
        "warnings": [str(w) for w in warnings] if isinstance(warnings, list) else [],
        "skipped_assets": [str(s) for s in skipped] if isinstance(skipped, list) else [],
        "scanner_errors": [str(e) for e in scanner_errors] if isinstance(scanner_errors, list) else [],
    }


def warnings_from_run_metadata(raw: dict[str, Any] | None) -> list[str]:
    return parse_run_metadata(raw)["warnings"]
