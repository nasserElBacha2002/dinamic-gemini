"""Tests for :mod:`src.application.services.reference_usage_from_job_result`."""

from __future__ import annotations

from src.application.services.reference_usage_from_job_result import (
    parse_reference_usage_from_result_json,
)
from src.pipeline.run_metadata import RUN_METADATA_KEY_VISUAL_REFERENCE_CONTEXT


def test_parse_none_when_not_dict() -> None:
    assert parse_reference_usage_from_result_json(None) is None
    assert parse_reference_usage_from_result_json([]) is None


def test_parse_none_when_context_missing() -> None:
    assert parse_reference_usage_from_result_json({}) is None
    assert parse_reference_usage_from_result_json({"other": {}}) is None


def test_parse_deduplicates_reference_ids_preserves_order() -> None:
    raw = {
        RUN_METADATA_KEY_VISUAL_REFERENCE_CONTEXT: {
            "resolved": True,
            "resolved_count": "3",
            "provider_consumed": 0,
            "provider_consumed_count": 2.7,
            "reference_ids": ["a", "a", "", "  b  ", "b"],
            "resolution_error": "x" * 3000,
        }
    }
    f = parse_reference_usage_from_result_json(raw)
    assert f is not None
    assert f.resolved is True
    assert f.resolved_count == 3
    assert f.provider_consumed is False
    assert f.provider_consumed_count == 2
    assert f.reference_ids == ["a", "b"]
    assert f.resolution_error is not None and len(f.resolution_error) == 2048
