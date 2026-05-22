"""Unit tests for analytics cost snapshot parsing."""

from __future__ import annotations

import pytest

from src.application.services.analytics_cost_snapshot_parser import parse_llm_cost_snapshot


def _snapshot(
    *,
    capture_status: str = "exact",
    total_cost: str | None = "0.01000000",
    provider: str = "gemini",
    model: str = "gemini-2.0",
) -> dict:
    return {
        "llm_cost_snapshot": {
            "provider": provider,
            "model": model,
            "usage": {
                "input_tokens": 1,
                "output_tokens": 1,
                "cached_input_tokens": 0,
                "cache_write_tokens": 0,
                "thinking_tokens": 0,
                "tool_request_count": 0,
                "image_input_count": 0,
                "audio_input_tokens": 0,
                "video_input_tokens": 0,
            },
            "pricing_snapshot": {
                "pricing_source": "catalog",
                "billing_currency": "USD",
            },
            "computed_cost": {
                "total_cost": total_cost,
                "currency": "USD",
            },
            "capture_status": capture_status,
            "capture_notes": [],
        }
    }


@pytest.mark.parametrize(
    "capture_status",
    ["exact", "estimated", "partial", "unavailable"],
)
def test_parse_valid_capture_statuses(capture_status: str) -> None:
    parsed = parse_llm_cost_snapshot(_snapshot(capture_status=capture_status))
    assert parsed.capture_status == capture_status
    if capture_status in ("exact", "estimated"):
        assert parsed.cost_amount is not None
    if capture_status == "partial":
        parsed_partial = parse_llm_cost_snapshot(_snapshot(capture_status="partial", total_cost=None))
        assert parsed_partial.cost_amount is None


def test_parse_unknown_capture_status_maps_to_unavailable() -> None:
    parsed = parse_llm_cost_snapshot(_snapshot(capture_status="bogus_status"))
    assert parsed.capture_status == "unavailable"


def test_parse_unavailable_with_numeric_cost_keeps_parsed_amount() -> None:
    parsed = parse_llm_cost_snapshot(_snapshot(capture_status="unavailable", total_cost="123.00000000"))
    assert parsed.capture_status == "unavailable"
    assert parsed.cost_amount is not None


def test_parse_missing_snapshot() -> None:
    parsed = parse_llm_cost_snapshot({})
    assert parsed.capture_status == "missing"
    assert parsed.cost_amount is None
    assert parsed.has_snapshot is False


def test_parse_malformed_result_json() -> None:
    parsed = parse_llm_cost_snapshot(None)
    assert parsed.capture_status == "missing"


def test_parse_non_numeric_computed_cost() -> None:
    parsed = parse_llm_cost_snapshot(_snapshot(total_cost="not-a-number"))
    assert parsed.cost_amount is None
    assert "invalid_computed_cost" in parsed.warnings


def test_parse_negative_computed_cost() -> None:
    parsed = parse_llm_cost_snapshot(_snapshot(total_cost="-1"))
    assert parsed.cost_amount is None
    assert "invalid_computed_cost" in parsed.warnings


def test_parse_null_computed_cost() -> None:
    parsed = parse_llm_cost_snapshot(_snapshot(total_cost=None, capture_status="unavailable"))
    assert parsed.cost_amount is None
