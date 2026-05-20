"""Tests for code scan run metadata helpers."""

from __future__ import annotations

from src.application.services.code_scan_run_metadata import (
    build_run_metadata,
    parse_run_metadata,
    warnings_from_run_metadata,
)


def test_legacy_warnings_only_metadata() -> None:
    meta = {"warnings": ["legacy warn"]}
    parsed = parse_run_metadata(meta)
    assert parsed["warnings"] == ["legacy warn"]
    assert parsed["skipped_assets"] == []
    assert parsed["scanner_errors"] == []
    assert warnings_from_run_metadata(meta) == ["legacy warn"]


def test_build_run_metadata_stable_shape() -> None:
    skipped = [{"asset_id": "asset-v", "reason": "unsupported_asset_type", "asset_type": "video"}]
    meta = build_run_metadata(
        warnings=["w1"],
        skipped_assets=skipped,
        scanner_errors=["asset-v: boom"],
        unreadable_assets=[{"asset_id": "a2", "reason": "storage_read_failed"}],
    )
    assert meta["warnings"] == ["w1"]
    assert meta["skipped_assets"] == skipped
    assert meta["scanner_errors"] == ["asset-v: boom"]
    assert meta["unreadable_assets"] == [{"asset_id": "a2", "reason": "storage_read_failed"}]
    assert meta["unsupported_assets"] == []
