"""Golden / characterization tests for :func:`build_llm_cost_snapshot` (Phase 0)."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.llm.costing import build_llm_cost_snapshot

_FIXED_CAPTURED_AT = "2026-05-19T12:00:00Z"


def _settings_with_catalog(catalog: dict) -> SimpleNamespace:
    return SimpleNamespace(
        llm_pricing_catalog_json=json.dumps(catalog),
        llm_pricing_catalog_version="",
    )


@pytest.fixture
def fixed_captured_at() -> None:
    with patch("src.llm.costing._utc_iso_now", return_value=_FIXED_CAPTURED_AT):
        yield


def _build(**kwargs: object) -> dict:
    return build_llm_cost_snapshot(**kwargs)  # type: ignore[arg-type]


_GOLDEN_EXACT = {
    "billing_currency": "USD",
    "canonical_model": "gpt-4o",
    "capture_notes": [],
    "capture_status": "exact",
    "computed_cost": {
        "currency": "USD",
        "partial_total_cost": None,
        "subtotal_audio": None,
        "subtotal_cache_write": None,
        "subtotal_cached": "0.00000000",
        "subtotal_image": None,
        "subtotal_input": "0.00500000",
        "subtotal_output": "0.00750000",
        "subtotal_thinking": None,
        "subtotal_tools": None,
        "subtotal_video": None,
        "total_cost": "0.01250000",
        "total_cost_unavailable_reason": None,
    },
    "model": "gpt-4o",
    "pricing_available": True,
    "pricing_snapshot": {
        "audio_input_cost_per_million": None,
        "billing_currency": "USD",
        "cache_write_cost_per_million": None,
        "cached_input_cost_per_million": "1.00000000",
        "canonical_model": "gpt-4o",
        "captured_at": _FIXED_CAPTURED_AT,
        "image_input_unit_cost": None,
        "input_cost_per_million": "5.00000000",
        "model": "gpt-4o",
        "output_cost_per_million": "15.00000000",
        "price_units": "per_1m_tokens",
        "pricing_catalog_entry_captured_at": None,
        "pricing_confidence": "operator_approved",
        "pricing_source": "settings.llm_pricing_catalog_json+dinamic_embedded_placeholders",
        "pricing_version": "catalog-v1",
        "provider": "openai",
        "thinking_billed_as": None,
        "thinking_cost_per_million": None,
        "thinking_cost_rule": None,
        "tool_request_unit_cost": None,
        "video_input_cost_per_million": None,
    },
    "provider": "openai",
    "usage": {
        "audio_input_tokens": None,
        "cache_write_tokens": None,
        "cached_input_tokens": 0,
        "image_input_count": None,
        "image_input_tokens": None,
        "input_tokens": 1000,
        "output_tokens": 500,
        "raw_provider_usage_json": {
            "completion_tokens": 500,
            "prompt_tokens": 1000,
            "prompt_tokens_details": {"cached_tokens": 0},
            "total_tokens": 1500,
        },
        "thinking_tokens": None,
        "tool_requests": None,
        "total_tokens": 1500,
        "video_input_tokens": None,
    },
}

_GOLDEN_PARTIAL = {
    "billing_currency": "USD",
    "canonical_model": "gpt-4o",
    "capture_notes": ["billable_dimension_not_priced:output_tokens"],
    "capture_status": "partial",
    "computed_cost": {
        "currency": "USD",
        "partial_total_cost": "0.00050000",
        "subtotal_audio": None,
        "subtotal_cache_write": None,
        "subtotal_cached": None,
        "subtotal_image": None,
        "subtotal_input": "0.00050000",
        "subtotal_output": None,
        "subtotal_thinking": None,
        "subtotal_tools": None,
        "subtotal_video": None,
        "total_cost": None,
        "total_cost_unavailable_reason": "billable_dimension_not_priced",
    },
    "model": "gpt-4o",
    "pricing_available": True,
    "pricing_snapshot": {
        "audio_input_cost_per_million": None,
        "billing_currency": "USD",
        "cache_write_cost_per_million": None,
        "cached_input_cost_per_million": None,
        "canonical_model": "gpt-4o",
        "captured_at": _FIXED_CAPTURED_AT,
        "image_input_unit_cost": None,
        "input_cost_per_million": "5.00000000",
        "model": "gpt-4o",
        "output_cost_per_million": None,
        "price_units": "per_1m_tokens",
        "pricing_catalog_entry_captured_at": None,
        "pricing_confidence": "operator_approved",
        "pricing_source": "settings.llm_pricing_catalog_json+dinamic_embedded_placeholders",
        "pricing_version": "dinamic-embedded-pricing-v2",
        "provider": "openai",
        "thinking_billed_as": None,
        "thinking_cost_per_million": None,
        "thinking_cost_rule": None,
        "tool_request_unit_cost": None,
        "video_input_cost_per_million": None,
    },
    "provider": "openai",
    "usage": {
        "audio_input_tokens": None,
        "cache_write_tokens": None,
        "cached_input_tokens": 0,
        "image_input_count": None,
        "image_input_tokens": None,
        "input_tokens": 100,
        "output_tokens": 50,
        "raw_provider_usage_json": {
            "completion_tokens": 50,
            "prompt_tokens": 100,
            "prompt_tokens_details": {"cached_tokens": 0},
            "total_tokens": 150,
        },
        "thinking_tokens": None,
        "tool_requests": None,
        "total_tokens": 150,
        "video_input_tokens": None,
    },
}

_GOLDEN_UNAVAILABLE = {
    "billing_currency": "USD",
    "canonical_model": "gemini-2.0-flash-exp",
    "capture_notes": [
        "billable_dimension_not_priced:input_tokens",
        "billable_dimension_not_priced:output_tokens",
        "pricing_entry_missing:provider=gemini,model=gemini-2.0-flash-exp,canonical_model=gemini-2.0-flash-exp",
    ],
    "capture_status": "unavailable",
    "computed_cost": {
        "currency": "USD",
        "partial_total_cost": None,
        "subtotal_audio": None,
        "subtotal_cache_write": None,
        "subtotal_cached": None,
        "subtotal_image": None,
        "subtotal_input": None,
        "subtotal_output": None,
        "subtotal_thinking": None,
        "subtotal_tools": None,
        "subtotal_video": None,
        "total_cost": None,
        "total_cost_unavailable_reason": "pricing_entry_missing",
    },
    "model": "gemini-2.0-flash-exp",
    "pricing_available": False,
    "pricing_snapshot": {
        "audio_input_cost_per_million": None,
        "billing_currency": "USD",
        "cache_write_cost_per_million": None,
        "cached_input_cost_per_million": None,
        "canonical_model": "gemini-2.0-flash-exp",
        "captured_at": _FIXED_CAPTURED_AT,
        "image_input_unit_cost": None,
        "input_cost_per_million": None,
        "model": "gemini-2.0-flash-exp",
        "output_cost_per_million": None,
        "price_units": "per_1m_tokens",
        "pricing_catalog_entry_captured_at": None,
        "pricing_confidence": "unknown",
        "pricing_source": "settings.llm_pricing_catalog_json+dinamic_embedded_placeholders",
        "pricing_version": "catalog-v1",
        "provider": "gemini",
        "thinking_billed_as": None,
        "thinking_cost_per_million": None,
        "thinking_cost_rule": None,
        "tool_request_unit_cost": None,
        "video_input_cost_per_million": None,
    },
    "provider": "gemini",
    "usage": {
        "audio_input_tokens": None,
        "cache_write_tokens": None,
        "cached_input_tokens": 0,
        "image_input_count": None,
        "image_input_tokens": None,
        "input_tokens": 200,
        "output_tokens": 100,
        "raw_provider_usage_json": {
            "cached_content_token_count": 0,
            "candidates_token_count": 100,
            "prompt_token_count": 200,
            "total_token_count": 300,
        },
        "thinking_tokens": None,
        "tool_requests": None,
        "total_tokens": 300,
        "video_input_tokens": None,
    },
}

_GOLDEN_GEMINI_THINKING = {
    "billing_currency": "USD",
    "canonical_model": "gemini-2.5-pro",
    "capture_notes": [],
    "capture_status": "exact",
    "computed_cost": {
        "currency": "USD",
        "partial_total_cost": None,
        "subtotal_audio": None,
        "subtotal_cache_write": None,
        "subtotal_cached": None,
        "subtotal_image": None,
        "subtotal_input": "0.00010000",
        "subtotal_output": "0.00010000",
        "subtotal_thinking": None,
        "subtotal_tools": None,
        "subtotal_video": None,
        "total_cost": "0.00020000",
        "total_cost_unavailable_reason": None,
    },
    "model": "gemini-2.5-pro",
    "pricing_available": True,
    "pricing_snapshot": {
        "audio_input_cost_per_million": None,
        "billing_currency": "USD",
        "cache_write_cost_per_million": None,
        "cached_input_cost_per_million": None,
        "canonical_model": "gemini-2.5-pro",
        "captured_at": _FIXED_CAPTURED_AT,
        "image_input_unit_cost": None,
        "input_cost_per_million": "1.00000000",
        "model": "gemini-2.5-pro",
        "output_cost_per_million": "2.00000000",
        "price_units": "per_1m_tokens",
        "pricing_catalog_entry_captured_at": None,
        "pricing_confidence": "operator_approved",
        "pricing_source": "settings.llm_pricing_catalog_json+dinamic_embedded_placeholders",
        "pricing_version": "dinamic-embedded-pricing-v2",
        "provider": "gemini",
        "thinking_billed_as": "output_tokens",
        "thinking_cost_per_million": None,
        "thinking_cost_rule": None,
        "tool_request_unit_cost": None,
        "video_input_cost_per_million": None,
    },
    "provider": "gemini",
    "usage": {
        "audio_input_tokens": None,
        "cache_write_tokens": None,
        "cached_input_tokens": 0,
        "image_input_count": None,
        "image_input_tokens": None,
        "input_tokens": 100,
        "output_tokens": 40,
        "raw_provider_usage_json": {
            "cached_content_token_count": 0,
            "candidates_token_count": 40,
            "prompt_token_count": 100,
            "thoughts_token_count": 10,
        },
        "thinking_tokens": 10,
        "tool_requests": None,
        "total_tokens": None,
        "video_input_tokens": None,
    },
}

_GOLDEN_OPENAI_CACHED = {
    "billing_currency": "USD",
    "canonical_model": "gpt-4o",
    "capture_notes": [],
    "capture_status": "exact",
    "computed_cost": {
        "currency": "USD",
        "partial_total_cost": None,
        "subtotal_audio": None,
        "subtotal_cache_write": None,
        "subtotal_cached": "0.00002000",
        "subtotal_image": None,
        "subtotal_input": "0.00040000",
        "subtotal_output": "0.00075000",
        "subtotal_thinking": None,
        "subtotal_tools": None,
        "subtotal_video": None,
        "total_cost": "0.00117000",
        "total_cost_unavailable_reason": None,
    },
    "model": "gpt-4o",
    "pricing_available": True,
    "pricing_snapshot": {
        "audio_input_cost_per_million": None,
        "billing_currency": "USD",
        "cache_write_cost_per_million": None,
        "cached_input_cost_per_million": "1.00000000",
        "canonical_model": "gpt-4o",
        "captured_at": _FIXED_CAPTURED_AT,
        "image_input_unit_cost": None,
        "input_cost_per_million": "5.00000000",
        "model": "gpt-4o",
        "output_cost_per_million": "15.00000000",
        "price_units": "per_1m_tokens",
        "pricing_catalog_entry_captured_at": None,
        "pricing_confidence": "operator_approved",
        "pricing_source": "settings.llm_pricing_catalog_json+dinamic_embedded_placeholders",
        "pricing_version": "dinamic-embedded-pricing-v2",
        "provider": "openai",
        "thinking_billed_as": None,
        "thinking_cost_per_million": None,
        "thinking_cost_rule": None,
        "tool_request_unit_cost": None,
        "video_input_cost_per_million": None,
    },
    "provider": "openai",
    "usage": {
        "audio_input_tokens": None,
        "cache_write_tokens": None,
        "cached_input_tokens": 20,
        "image_input_count": None,
        "image_input_tokens": None,
        "input_tokens": 80,
        "output_tokens": 50,
        "raw_provider_usage_json": {
            "completion_tokens": 50,
            "prompt_tokens": 100,
            "prompt_tokens_details": {"cached_tokens": 20},
            "total_tokens": 150,
        },
        "thinking_tokens": None,
        "tool_requests": None,
        "total_tokens": 150,
        "video_input_tokens": None,
    },
}

_GOLDEN_ALIAS_UNAVAILABLE = {
    "billing_currency": "USD",
    "canonical_model": "gpt-not-in-catalog",
    "capture_notes": [
        "billable_dimension_not_priced:input_tokens",
        "canonical_model_without_catalog_entry:provider=openai,model=my-short,canonical_model=gpt-not-in-catalog",
    ],
    "capture_status": "unavailable",
    "computed_cost": {
        "currency": "USD",
        "partial_total_cost": None,
        "subtotal_audio": None,
        "subtotal_cache_write": None,
        "subtotal_cached": None,
        "subtotal_image": None,
        "subtotal_input": None,
        "subtotal_output": None,
        "subtotal_thinking": None,
        "subtotal_tools": None,
        "subtotal_video": None,
        "total_cost": None,
        "total_cost_unavailable_reason": "canonical_model_without_catalog_entry",
    },
    "model": "my-short",
    "pricing_available": False,
    "pricing_snapshot": {
        "audio_input_cost_per_million": None,
        "billing_currency": "USD",
        "cache_write_cost_per_million": None,
        "cached_input_cost_per_million": None,
        "canonical_model": "gpt-not-in-catalog",
        "captured_at": _FIXED_CAPTURED_AT,
        "image_input_unit_cost": None,
        "input_cost_per_million": None,
        "model": "my-short",
        "output_cost_per_million": None,
        "price_units": "per_1m_tokens",
        "pricing_catalog_entry_captured_at": None,
        "pricing_confidence": "unknown",
        "pricing_source": "settings.llm_pricing_catalog_json+dinamic_embedded_placeholders",
        "pricing_version": "v1",
        "provider": "openai",
        "thinking_billed_as": None,
        "thinking_cost_per_million": None,
        "thinking_cost_rule": None,
        "tool_request_unit_cost": None,
        "video_input_cost_per_million": None,
    },
    "provider": "openai",
    "usage": {
        "audio_input_tokens": None,
        "cache_write_tokens": None,
        "cached_input_tokens": 0,
        "image_input_count": None,
        "image_input_tokens": None,
        "input_tokens": 100,
        "output_tokens": 0,
        "raw_provider_usage_json": {
            "completion_tokens": 0,
            "prompt_tokens": 100,
            "prompt_tokens_details": {"cached_tokens": 0},
            "total_tokens": 100,
        },
        "thinking_tokens": None,
        "tool_requests": None,
        "total_tokens": 100,
        "video_input_tokens": None,
    },
}


@pytest.mark.parametrize(
    ("expected", "kwargs"),
    [
        (
            _GOLDEN_EXACT,
            {
                "provider": "openai",
                "model": "gpt-4o",
                "raw_usage": {
                    "prompt_tokens": 1000,
                    "completion_tokens": 500,
                    "total_tokens": 1500,
                    "prompt_tokens_details": {"cached_tokens": 0},
                },
                "settings": _settings_with_catalog(
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
                ),
            },
        ),
        (
            _GOLDEN_PARTIAL,
            {
                "provider": "openai",
                "model": "gpt-4o",
                "raw_usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 50,
                    "total_tokens": 150,
                    "prompt_tokens_details": {"cached_tokens": 0},
                },
                "settings": _settings_with_catalog(
                    {
                        "currency": "USD",
                        "entries": [
                            {
                                "provider": "openai",
                                "model": "gpt-4o",
                                "input_cost_per_million": 5,
                            }
                        ],
                    }
                ),
            },
        ),
        (
            _GOLDEN_UNAVAILABLE,
            {
                "provider": "gemini",
                "model": "gemini-2.0-flash-exp",
                "raw_usage": {
                    "prompt_token_count": 200,
                    "candidates_token_count": 100,
                    "total_token_count": 300,
                    "cached_content_token_count": 0,
                },
                "settings": _settings_with_catalog(
                    {"version": "catalog-v1", "currency": "USD", "entries": []}
                ),
            },
        ),
        (
            _GOLDEN_GEMINI_THINKING,
            {
                "provider": "gemini",
                "model": "gemini-2.5-pro",
                "raw_usage": {
                    "prompt_token_count": 100,
                    "candidates_token_count": 40,
                    "thoughts_token_count": 10,
                    "cached_content_token_count": 0,
                },
                "settings": _settings_with_catalog(
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
                ),
            },
        ),
        (
            _GOLDEN_OPENAI_CACHED,
            {
                "provider": "openai",
                "model": "gpt-4o",
                "raw_usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 50,
                    "total_tokens": 150,
                    "prompt_tokens_details": {"cached_tokens": 20},
                },
                "settings": _settings_with_catalog(
                    {
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
                ),
            },
        ),
        (
            _GOLDEN_ALIAS_UNAVAILABLE,
            {
                "provider": "openai",
                "model": "my-short",
                "raw_usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 0,
                    "total_tokens": 100,
                    "prompt_tokens_details": {"cached_tokens": 0},
                },
                "settings": _settings_with_catalog(
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
                ),
            },
        ),
    ],
)
def test_build_llm_cost_snapshot_golden(
    fixed_captured_at: None,
    expected: dict,
    kwargs: dict,
) -> None:
    snap = _build(**kwargs)
    assert snap == expected
