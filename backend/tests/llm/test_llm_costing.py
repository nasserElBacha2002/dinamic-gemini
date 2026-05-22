from __future__ import annotations

import json
from types import SimpleNamespace

from src.application.use_cases.shared.benchmark_compare_support import (
    sanitize_llm_cost_snapshot_for_compare,
)
from src.llm.costing import (
    build_llm_cost_snapshot,
    normalize_usage,
    resolve_pricing_with_canonical,
    validate_llm_pricing_coverage,
)


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
    assert "usage_assumption:claude_input_tokens_non_cache_or_provider_reported" in notes


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
    assert snap["pricing_snapshot"]["pricing_confidence"] == "operator_approved"
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


def test_embedded_defaults_match_openai_gpt_5_4_case_insensitive() -> None:
    settings = SimpleNamespace(llm_pricing_catalog_json="", llm_pricing_catalog_version="")
    snap = build_llm_cost_snapshot(
        provider="openai",
        model="GPT-5.4",
        raw_usage={
            "prompt_tokens": 1_000_000,
            "completion_tokens": 0,
            "total_tokens": 1_000_000,
            "prompt_tokens_details": {"cached_tokens": 0},
        },
        settings=settings,
    )
    assert snap["pricing_available"] is True
    assert "pricing_entry_missing" not in snap["capture_notes"]
    assert snap["computed_cost"]["total_cost"] == "5.00000000"
    assert snap["computed_cost"]["total_cost_unavailable_reason"] is None
    assert snap["pricing_snapshot"]["pricing_confidence"] == "embedded_placeholder"
    assert snap["capture_status"] == "estimated"
    assert "usage_assumption:embedded_pricing_placeholder_not_finance_approved" in snap["capture_notes"]


def test_embedded_defaults_match_claude_sonnet_4_20250514() -> None:
    settings = SimpleNamespace(llm_pricing_catalog_json="", llm_pricing_catalog_version="")
    snap = build_llm_cost_snapshot(
        provider="claude",
        model="claude-sonnet-4-20250514",
        raw_usage={"input_tokens": 1_000_000, "output_tokens": 0},
        settings=settings,
    )
    assert snap["pricing_available"] is True
    assert snap["computed_cost"]["total_cost"] == "3.00000000"
    assert snap["pricing_snapshot"]["pricing_confidence"] == "embedded_placeholder"
    assert snap["capture_status"] == "estimated"
    assert "usage_assumption:embedded_pricing_placeholder_not_finance_approved" in snap["capture_notes"]


def test_build_llm_cost_snapshot_unavailable_missing_pricing_entry() -> None:
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
    assert snap["capture_status"] == "unavailable"
    assert snap["computed_cost"]["total_cost"] is None
    assert any(n.startswith("pricing_entry_missing") for n in snap["capture_notes"])
    assert snap["pricing_available"] is False
    assert snap["computed_cost"]["total_cost_unavailable_reason"] == "pricing_entry_missing"


def test_build_llm_cost_snapshot_partial_when_output_unpriced() -> None:
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
    assert snap["capture_status"] == "partial"
    assert snap["computed_cost"]["total_cost"] is None
    assert snap["computed_cost"]["partial_total_cost"] == "0.00050000"
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


def test_build_llm_cost_snapshot_exact_when_usage_metadata_present_all_zero() -> None:
    settings = _settings_with_catalog(
        {
            "currency": "USD",
            "entries": [{"provider": "openai", "model": "gpt-4o", "input_cost_per_million": 5}],
        }
    )
    snap = build_llm_cost_snapshot(
        provider="openai",
        model="gpt-4o",
        raw_usage={
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "prompt_tokens_details": {"cached_tokens": 0},
        },
        settings=settings,
    )
    assert snap["capture_status"] == "exact"
    assert snap["pricing_snapshot"]["pricing_confidence"] == "operator_approved"
    assert "provider_usage_missing" not in snap["capture_notes"]


def test_build_llm_cost_snapshot_partial_when_cache_write_unpriced() -> None:
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
    assert snap["capture_status"] == "partial"
    assert snap["computed_cost"]["total_cost"] is None
    assert snap["computed_cost"]["partial_total_cost"] is not None
    assert "billable_dimension_not_priced:cache_write_tokens" in snap["capture_notes"]


def test_build_llm_cost_snapshot_estimated_for_claude_cache_read_assumption() -> None:
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
    assert "usage_assumption:claude_input_tokens_non_cache_or_provider_reported" in snap["capture_notes"]
    assert snap["computed_cost"]["total_cost"] is not None


def test_build_llm_cost_snapshot_exact_when_zero_usage_no_notes() -> None:
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
    assert snap["capture_status"] == "exact"
    assert snap["pricing_snapshot"]["pricing_confidence"] == "operator_approved"
    assert snap["computed_cost"]["total_cost"] == "0.00000000"
    assert "provider_usage_missing" not in snap["capture_notes"]
    assert "pricing_present_but_no_billable_dimensions" not in snap["capture_notes"]


def test_resolve_pricing_alias_to_canonical_entry() -> None:
    catalog = {
        "version": "t",
        "currency": "USD",
        "source": "test",
        "entries": [
            {
                "provider": "claude",
                "model": "claude-opus-4",
                "input_cost_per_million": 10,
                "output_cost_per_million": 20,
            }
        ],
        "aliases": [
            {
                "provider": "claude",
                "alias": "claude-opus-4-7",
                "canonical_model": "claude-opus-4",
            }
        ],
    }
    res = resolve_pricing_with_canonical(catalog, "claude", "claude-opus-4-7")
    assert res.entry is not None
    assert res.canonical_model == "claude-opus-4"


def test_resolve_pricing_wildcard_when_model_unknown() -> None:
    catalog = {
        "version": "t",
        "currency": "USD",
        "source": "test",
        "entries": [
            {
                "provider": "claude",
                "model": "*",
                "input_cost_per_million": 1,
                "output_cost_per_million": 2,
            }
        ],
        "aliases": [],
    }
    res = resolve_pricing_with_canonical(catalog, "claude", "unknown-model-xyz")
    assert res.entry is not None
    assert res.entry.get("model") == "*"


def test_build_llm_cost_snapshot_exact_when_cache_write_priced() -> None:
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
                    "cache_write_cost_per_million": 2,
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
    assert snap["capture_status"] == "exact"
    assert snap["pricing_snapshot"]["pricing_confidence"] == "operator_approved"
    assert snap["computed_cost"]["subtotal_cache_write"] is not None
    assert snap["computed_cost"]["total_cost"] is not None


def test_build_llm_cost_snapshot_gemini_thinking_billed_as_output() -> None:
    settings = _settings_with_catalog(
        {
            "currency": "USD",
            "entries": [
                {
                    "provider": "gemini",
                    "model": "gemini-2.5-pro",
                    "input_cost_per_million": 1,
                    "output_cost_per_million": 2,
                    "thinking_billed_as": "output_tokens",
                }
            ],
        }
    )
    snap = build_llm_cost_snapshot(
        provider="gemini",
        model="gemini-2.5-pro",
        raw_usage={
            "prompt_token_count": 100,
            "candidates_token_count": 40,
            "thoughts_token_count": 10,
            "cached_content_token_count": 0,
        },
        settings=settings,
    )
    assert snap["capture_status"] == "exact"
    assert snap["pricing_snapshot"]["pricing_confidence"] == "operator_approved"
    assert "usage_dimension_ambiguous:output_tokens" not in snap["capture_notes"]


def test_validate_llm_pricing_coverage_flags_unknown_model() -> None:
    settings = SimpleNamespace(
        llm_pricing_catalog_json=json.dumps({"version": "x", "currency": "USD", "entries": []}),
        llm_pricing_catalog_version="",
        processing_openai_models="openai-model-not-in-any-catalog",
        processing_gemini_models="",
        processing_claude_models="",
        anthropic_model="",
        gemini_model_name="",
        openai_model="",
    )
    issues = validate_llm_pricing_coverage(settings)
    assert any(
        i.provider == "openai"
        and i.raw_model == "openai-model-not-in-any-catalog"
        and not i.has_entry
        and i.missing_reason == "pricing_entry_missing"
        for i in issues
    )


def test_validate_llm_pricing_coverage_alias_without_catalog_entry() -> None:
    settings = SimpleNamespace(
        llm_pricing_catalog_json=json.dumps(
            {
                "version": "x",
                "currency": "USD",
                "entries": [],
                "aliases": [
                    {
                        "provider": "openai",
                        "alias": "configured-alias",
                        "canonical_model": "missing-canonical",
                    }
                ],
            }
        ),
        llm_pricing_catalog_version="",
        processing_openai_models="configured-alias",
        processing_gemini_models="",
        processing_claude_models="",
        anthropic_model="",
        gemini_model_name="",
        openai_model="",
    )
    issues = validate_llm_pricing_coverage(settings)
    miss = [i for i in issues if i.raw_model == "configured-alias" and not i.has_entry]
    assert len(miss) == 1
    assert miss[0].missing_reason == "canonical_model_without_catalog_entry"


def test_build_llm_cost_snapshot_alias_without_catalog_entry_unavailable() -> None:
    settings = _settings_with_catalog(
        {
            "version": "v1",
            "currency": "USD",
            "entries": [],
            "aliases": [
                {
                    "provider": "openai",
                    "alias": "my-short",
                    "canonical_model": "gpt-not-in-catalog",
                }
            ],
        }
    )
    snap = build_llm_cost_snapshot(
        provider="openai",
        model="my-short",
        raw_usage={
            "prompt_tokens": 100,
            "completion_tokens": 0,
            "total_tokens": 100,
            "prompt_tokens_details": {"cached_tokens": 0},
        },
        settings=settings,
    )
    assert snap["capture_status"] == "unavailable"
    assert snap["pricing_snapshot"]["pricing_confidence"] == "unknown"
    assert any(n.startswith("canonical_model_without_catalog_entry:") for n in snap["capture_notes"])
    assert snap["computed_cost"]["total_cost_unavailable_reason"] == "canonical_model_without_catalog_entry"


def test_sanitize_llm_cost_snapshot_for_compare_strips_raw_usage() -> None:
    snap = {
        "usage": {"input_tokens": 3, "raw_provider_usage_json": {"prompt_tokens": 3}},
        "computed_cost": {},
    }
    out = sanitize_llm_cost_snapshot_for_compare(snap)
    assert "raw_provider_usage_json" not in out["usage"]


def test_costing_public_imports_remain_available() -> None:
    from src.llm.costing import (
        PricingCoverageIssue,
        build_llm_cost_snapshot,
        normalize_usage,
        resolve_pricing_with_canonical,
        validate_llm_pricing_coverage,
    )

    assert PricingCoverageIssue is not None
    assert build_llm_cost_snapshot is not None
    assert normalize_usage is not None
    assert resolve_pricing_with_canonical is not None
    assert validate_llm_pricing_coverage is not None


def test_costing_private_total_cost_unavailable_reason_import() -> None:
    from src.llm.costing import _total_cost_unavailable_reason

    assert _total_cost_unavailable_reason is not None
