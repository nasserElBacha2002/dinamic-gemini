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
    meta = build_run_metadata(
        warnings=["w1"],
        skipped_assets=["asset-v"],
        scanner_errors=["asset-v: boom"],
    )
    assert meta == {
        "warnings": ["w1"],
        "skipped_assets": ["asset-v"],
        "scanner_errors": ["asset-v: boom"],
    }
