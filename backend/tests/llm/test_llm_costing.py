from __future__ import annotations

import json
from types import SimpleNamespace

from src.llm.costing import build_llm_cost_snapshot, normalize_usage


def _settings_with_catalog(catalog: dict) -> SimpleNamespace:
    return SimpleNamespace(
        llm_pricing_catalog_json=json.dumps(catalog),
        llm_pricing_catalog_version="",
    )


def test_normalize_usage_openai_shape() -> None:
    raw = {"prompt_tokens": 120, "completion_tokens": 30, "total_tokens": 150}
    usage = normalize_usage("openai", raw)
    assert usage["input_tokens"] == 120
    assert usage["output_tokens"] == 30
    assert usage["total_tokens"] == 150


def test_normalize_usage_claude_shape() -> None:
    raw = {"input_tokens": 200, "output_tokens": 80}
    usage = normalize_usage("claude", raw)
    assert usage["input_tokens"] == 200
    assert usage["output_tokens"] == 80
    assert usage["total_tokens"] == 280


def test_build_llm_cost_snapshot_exact_when_usage_and_pricing_present() -> None:
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
                }
            ],
        }
    )
    snap = build_llm_cost_snapshot(
        provider="openai",
        model="gpt-4o",
        raw_usage={"prompt_tokens": 1000, "completion_tokens": 500},
        settings=settings,
    )
    assert snap["capture_status"] == "exact"
    assert snap["computed_cost"]["total_cost"] == "0.01250000"
    assert snap["computed_cost"]["currency"] == "USD"


def test_build_llm_cost_snapshot_estimated_without_pricing_entry() -> None:
    settings = _settings_with_catalog({"version": "catalog-v1", "currency": "USD", "entries": []})
    snap = build_llm_cost_snapshot(
        provider="gemini",
        model="gemini-2.0-flash-exp",
        raw_usage={"prompt_token_count": 200, "candidates_token_count": 100},
        settings=settings,
    )
    assert snap["capture_status"] == "estimated"
    assert snap["computed_cost"]["total_cost"] is None
    assert "pricing_entry_missing" in snap["capture_notes"]
