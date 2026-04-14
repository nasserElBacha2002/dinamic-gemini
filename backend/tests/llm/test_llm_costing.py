from __future__ import annotations

import json
from types import SimpleNamespace

from src.application.use_cases.benchmark_compare_support import sanitize_llm_cost_snapshot_for_compare
from src.llm.costing import build_llm_cost_snapshot, normalize_usage


def _settings_with_catalog(catalog: dict) -> SimpleNamespace:
    return SimpleNamespace(
        llm_pricing_catalog_json=json.dumps(catalog),
        llm_pricing_catalog_version="",
    )


def test_normalize_usage_openai_shape() -> None:
    raw = {"prompt_tokens": 120, "completion_tokens": 30, "total_tokens": 150}
    usage, notes = normalize_usage("openai", raw)
    assert usage["input_tokens"] == 120
    assert usage["output_tokens"] == 30
    assert usage["total_tokens"] == 150
    assert "usage_dimension_ambiguous:cached_input" in notes


def test_normalize_usage_openai_cached_split_from_details() -> None:
    raw = {
        "prompt_tokens": 100,
        "completion_tokens": 50,
        "total_tokens": 150,
        "prompt_tokens_details": {"cached_tokens": 20},
    }
    usage, notes = normalize_usage("openai", raw)
    assert usage["input_tokens"] == 80
    assert usage["cached_input_tokens"] == 20
    assert "usage_dimension_ambiguous:cached_input" not in notes


def test_normalize_usage_claude_shape() -> None:
    raw = {"input_tokens": 200, "output_tokens": 80}
    usage, notes = normalize_usage("claude", raw)
    assert usage["input_tokens"] == 200
    assert usage["output_tokens"] == 80
    assert usage["total_tokens"] is None
    assert not notes


def test_normalize_usage_claude_cache_read_split() -> None:
    raw = {"input_tokens": 500, "output_tokens": 100, "cache_read_input_tokens": 200}
    usage, notes = normalize_usage("claude", raw)
    assert usage["input_tokens"] == 500
    assert usage["cached_input_tokens"] == 200
    assert usage["output_tokens"] == 100
    assert "usage_dimension_ambiguous:claude_cache_read_vs_gross_input" in notes


def test_normalize_usage_gemini_fields_without_derived_total_when_ambiguous() -> None:
    raw = {
        "prompt_token_count": 100,
        "candidates_token_count": 40,
        "thoughts_token_count": 10,
        "cached_content_token_count": 25,
    }
    usage, notes = normalize_usage("gemini", raw)
    assert usage["input_tokens"] == 75
    assert usage["cached_input_tokens"] == 25
    assert usage["output_tokens"] == 40
    assert usage["thinking_tokens"] == 10
    assert usage["total_tokens"] is None
    assert "usage_dimension_ambiguous:output_tokens" in notes


def test_normalize_usage_gemini_no_total_derivation_when_not_reported() -> None:
    raw = {"prompt_token_count": 10, "candidates_token_count": 5}
    usage, notes = normalize_usage("gemini", raw)
    assert usage["total_tokens"] is None


def test_build_llm_cost_snapshot_exact_when_fully_priced_no_ambiguity() -> None:
    settings = _settings_with_catalog(
        {
            "version": "catalog-v1",
            "currency": "USD",
            "entries": [
                {
                    "provider": "openai",
                    "model": "gpt-4o",
                    "input_cost_per_million": 5,
                    "output_cost_per_million": 15,
                    "cached_input_cost_per_million": 1,
                }
            ],
        }
    )
    snap = build_llm_cost_snapshot(
        provider="openai",
        model="gpt-4o",
        raw_usage={
            "prompt_tokens": 1000,
            "completion_tokens": 500,
            "total_tokens": 1500,
            "prompt_tokens_details": {"cached_tokens": 0},
        },
        settings=settings,
    )
    assert snap["capture_status"] == "exact"
    assert snap["computed_cost"]["total_cost"] == "0.01250000"
    assert snap["computed_cost"]["currency"] == "USD"
    assert snap["pricing_snapshot"]["captured_at"]
    assert "Z" in snap["pricing_snapshot"]["captured_at"]
    assert snap["pricing_snapshot"]["pricing_catalog_entry_captured_at"] is None


def test_build_llm_cost_snapshot_preserves_catalog_entry_timestamp() -> None:
    settings = _settings_with_catalog(
        {
            "version": "catalog-v1",
            "currency": "USD",
            "entries": [
                {
                    "provider": "openai",
                    "model": "gpt-4o",
                    "captured_at": "2026-04-14T10:00:00Z",
                    "input_cost_per_million": 5,
                    "output_cost_per_million": 15,
                }
            ],
        }
    )
    snap = build_llm_cost_snapshot(
        provider="openai",
        model="gpt-4o",
        raw_usage={
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "prompt_tokens_details": {"cached_tokens": 0},
        },
        settings=settings,
    )
    assert snap["pricing_snapshot"]["captured_at"] is not None
    assert snap["pricing_snapshot"]["pricing_catalog_entry_captured_at"] == "2026-04-14T10:00:00Z"


def test_build_llm_cost_snapshot_estimated_missing_pricing_entry() -> None:
    settings = _settings_with_catalog({"version": "catalog-v1", "currency": "USD", "entries": []})
    snap = build_llm_cost_snapshot(
        provider="gemini",
        model="gemini-2.0-flash-exp",
        raw_usage={
            "prompt_token_count": 200,
            "candidates_token_count": 100,
            "total_token_count": 300,
            "cached_content_token_count": 0,
        },
        settings=settings,
    )
    assert snap["capture_status"] == "estimated"
    assert snap["computed_cost"]["total_cost"] is None
    assert "pricing_entry_missing" in snap["capture_notes"]


def test_build_llm_cost_snapshot_estimated_partial_pricing() -> None:
    settings = _settings_with_catalog(
        {
            "currency": "USD",
            "entries": [
                {
                    "provider": "openai",
                    "model": "gpt-4o",
                    "input_cost_per_million": 5,
                    # output price missing though usage has completion tokens
                }
            ],
        }
    )
    snap = build_llm_cost_snapshot(
        provider="openai",
        model="gpt-4o",
        raw_usage={
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "total_tokens": 150,
            "prompt_tokens_details": {"cached_tokens": 0},
        },
        settings=settings,
    )
    assert snap["capture_status"] == "estimated"
    assert "billable_dimension_not_priced:output_tokens" in snap["capture_notes"]


def test_build_llm_cost_snapshot_unavailable_no_usage() -> None:
    settings = _settings_with_catalog(
        {
            "currency": "USD",
            "entries": [{"provider": "x", "model": "y", "input_cost_per_million": 1}],
        }
    )
    snap = build_llm_cost_snapshot(provider="openai", model="y", raw_usage={}, settings=settings)
    assert snap["capture_status"] == "unavailable"
    assert "provider_usage_missing" in snap["capture_notes"]


def test_build_llm_cost_snapshot_estimated_when_usage_metadata_present_all_zero() -> None:
    settings = _settings_with_catalog(
        {
            "currency": "USD",
            "entries": [{"provider": "openai", "model": "gpt-4o", "input_cost_per_million": 5}],
        }
    )
    snap = build_llm_cost_snapshot(
        provider="openai",
        model="gpt-4o",
        raw_usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        settings=settings,
    )
    assert snap["capture_status"] == "estimated"
    assert "provider_usage_missing" not in snap["capture_notes"]


def test_build_llm_cost_snapshot_estimated_cache_write_unpriced() -> None:
    settings = _settings_with_catalog(
        {
            "currency": "USD",
            "entries": [
                {
                    "provider": "claude",
                    "model": "claude-sonnet-4",
                    "input_cost_per_million": 3,
                    "output_cost_per_million": 15,
                    "cached_input_cost_per_million": 1,
                }
            ],
        }
    )
    snap = build_llm_cost_snapshot(
        provider="claude",
        model="claude-sonnet-4",
        raw_usage={
            "input_tokens": 100,
            "output_tokens": 20,
            "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 50,
        },
        settings=settings,
    )
    assert snap["capture_status"] == "estimated"
    assert "billable_dimension_not_priced:cache_write_tokens" in snap["capture_notes"]


def test_build_llm_cost_snapshot_estimated_for_claude_cache_read_ambiguity() -> None:
    settings = _settings_with_catalog(
        {
            "currency": "USD",
            "entries": [
                {
                    "provider": "claude",
                    "model": "claude-sonnet-4",
                    "input_cost_per_million": 3,
                    "output_cost_per_million": 15,
                    "cached_input_cost_per_million": 1,
                }
            ],
        }
    )
    snap = build_llm_cost_snapshot(
        provider="claude",
        model="claude-sonnet-4",
        raw_usage={
            "input_tokens": 100,
            "output_tokens": 20,
            "cache_read_input_tokens": 20,
        },
        settings=settings,
    )
    assert snap["capture_status"] == "estimated"
    assert "usage_dimension_ambiguous:claude_cache_read_vs_gross_input" in snap["capture_notes"]


def test_build_llm_cost_snapshot_estimated_when_zero_usage_has_ambiguity_notes() -> None:
    settings = _settings_with_catalog(
        {
            "currency": "USD",
            "entries": [
                {
                    "provider": "openai",
                    "model": "gpt-4o",
                    "input_cost_per_million": 5,
                    "output_cost_per_million": 15,
                }
            ],
        }
    )
    snap = build_llm_cost_snapshot(
        provider="openai",
        model="gpt-4o",
        raw_usage={
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "prompt_tokens_details": {"cached_tokens": 0},
        },
        settings=settings,
    )
    assert snap["capture_status"] == "estimated"
    assert snap["computed_cost"]["total_cost"] == "0.00000000"
    assert "provider_usage_missing" not in snap["capture_notes"]
    assert "pricing_present_but_no_billable_dimensions" not in snap["capture_notes"]


def test_sanitize_llm_cost_snapshot_for_compare_strips_raw_usage() -> None:
    snap = {
        "usage": {"input_tokens": 3, "raw_provider_usage_json": {"prompt_tokens": 3}},
        "computed_cost": {},
    }
    out = sanitize_llm_cost_snapshot_for_compare(snap)
    assert "raw_provider_usage_json" not in out["usage"]
