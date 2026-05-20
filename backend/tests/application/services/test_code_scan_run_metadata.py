"""Tests for code scan run metadata helpers."""

from __future__ import annotations

from src.application.services.code_scan_run_metadata import (
    build_run_metadata,
    empty_run_metadata,
    parse_run_metadata,
    warnings_from_run_metadata,
)


def test_empty_metadata_returns_stable_shape() -> None:
    assert parse_run_metadata(None) == empty_run_metadata()
    assert parse_run_metadata({}) == empty_run_metadata()


def test_legacy_warnings_only_metadata() -> None:
    meta = {"warnings": ["legacy warn"]}
    parsed = parse_run_metadata(meta)
    assert parsed["warnings"] == ["legacy warn"]
    assert parsed["skipped_assets"] == []
    assert parsed["scanner_errors"] == []
    assert warnings_from_run_metadata(meta) == ["legacy warn"]


def test_legacy_skipped_assets_as_strings_normalizes() -> None:
    parsed = parse_run_metadata({"skipped_assets": ["asset-old", "asset-two"]})
    assert parsed["skipped_assets"] == [
        {"asset_id": "asset-old", "reason": "legacy_skipped"},
        {"asset_id": "asset-two", "reason": "legacy_skipped"},
    ]


def test_structured_skipped_assets_remain_structured() -> None:
    structured = [{"asset_id": "a1", "reason": "unsupported_asset_type", "asset_type": "video"}]
    parsed = parse_run_metadata({"skipped_assets": structured})
    assert parsed["skipped_assets"] == structured


def test_unreadable_assets_ignores_non_dict_values() -> None:
    parsed = parse_run_metadata(
        {
            "unreadable_assets": [
                {"asset_id": "a1", "reason": "unreadable_image"},
                "bad",
                42,
            ]
        }
    )
    assert parsed["unreadable_assets"] == [{"asset_id": "a1", "reason": "unreadable_image"}]


def test_unsupported_assets_ignores_non_dict_values() -> None:
    parsed = parse_run_metadata(
        {
            "unsupported_assets": [
                {"asset_id": "a2", "reason": "unsupported_image_format"},
                None,
            ]
        }
    )
    assert parsed["unsupported_assets"] == [
        {"asset_id": "a2", "reason": "unsupported_image_format"}
    ]


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
