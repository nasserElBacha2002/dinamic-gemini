"""Embedded default LLM pricing catalog (deployment placeholders)."""

from __future__ import annotations

from typing import Any

# Merged under operator JSON (``LLM_PRICING_CATALOG_JSON``); user entries override on same
# (provider, model) keys. USD values are deployment placeholders — override via env JSON for
# finance-approved list prices. Shape must match :func:`load_pricing_catalog`: ``entries`` +
# optional ``aliases`` (see H7).
EMBEDDED_DEFAULT_LLM_PRICING_CATALOG: dict[str, Any] = {
    "version": "dinamic-embedded-pricing-v2",
    "currency": "USD",
    "source": "dinamic_embedded_placeholders",
    "entries": [
        # OpenAI — aligned with typical PROCESSING_OPENAI_MODELS / OPENAI_MODEL
        {
            "provider": "openai",
            "model": "gpt-5.5",
            "input_cost_per_million": 5,
            "output_cost_per_million": 15,
            "cached_input_cost_per_million": 1.25,
        },
        {
            "provider": "openai",
            "model": "gpt-5.4",
            "input_cost_per_million": 5,
            "output_cost_per_million": 15,
            "cached_input_cost_per_million": 1.25,
        },
        {
            "provider": "openai",
            "model": "gpt-5.4-mini",
            "input_cost_per_million": 0.8,
            "output_cost_per_million": 2.4,
            "cached_input_cost_per_million": 0.16,
        },
        {
            "provider": "openai",
            "model": "gpt-5.4-nano",
            "input_cost_per_million": 0.2,
            "output_cost_per_million": 0.6,
            "cached_input_cost_per_million": 0.04,
        },
        {
            "provider": "openai",
            "model": "gpt-4o",
            "input_cost_per_million": 5,
            "output_cost_per_million": 15,
            "cached_input_cost_per_million": 1.25,
        },
        {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "input_cost_per_million": 0.15,
            "output_cost_per_million": 0.6,
            "cached_input_cost_per_million": 0.075,
        },
        {
            "provider": "openai",
            "model": "gpt-4-turbo",
            "input_cost_per_million": 10,
            "output_cost_per_million": 30,
            "cached_input_cost_per_million": 2.5,
        },
        # Anthropic — PROCESSING_CLAUDE_MODELS + ANTHROPIC_MODEL default
        {
            "provider": "claude",
            "model": "claude-sonnet-4-20250514",
            "input_cost_per_million": 3,
            "output_cost_per_million": 15,
            "cached_input_cost_per_million": 1,
        },
        {
            "provider": "claude",
            "model": "claude-3-5-sonnet-20241022",
            "input_cost_per_million": 3,
            "output_cost_per_million": 15,
            "cached_input_cost_per_million": 1,
        },
        {
            "provider": "claude",
            "model": "claude-opus-4-7",
            "input_cost_per_million": 15,
            "output_cost_per_million": 75,
            "cached_input_cost_per_million": 7.5,
        },
        {
            "provider": "claude",
            "model": "claude-sonnet-4-6",
            "input_cost_per_million": 3,
            "output_cost_per_million": 15,
            "cached_input_cost_per_million": 1,
        },
        {
            "provider": "claude",
            "model": "claude-haiku-4-5-20251001",
            "input_cost_per_million": 1,
            "output_cost_per_million": 5,
            "cached_input_cost_per_million": 0.5,
        },
        # Gemini — PROCESSING_GEMINI_MODELS / GEMINI_MODEL_NAME (thinking billed as output)
        {
            "provider": "gemini",
            "model": "gemini-2.5-pro",
            "input_cost_per_million": 1.25,
            "output_cost_per_million": 10,
            "cached_input_cost_per_million": 0.31,
            "thinking_billed_as": "output_tokens",
        },
        {
            "provider": "gemini",
            "model": "gemini-2.5-flash",
            "input_cost_per_million": 0.3,
            "output_cost_per_million": 2.5,
            "cached_input_cost_per_million": 0.08,
            "thinking_billed_as": "output_tokens",
        },
        {
            "provider": "gemini",
            "model": "gemini-3.1-flash-lite",
            "input_cost_per_million": 0.2,
            "output_cost_per_million": 0.6,
            "cached_input_cost_per_million": 0.05,
            "thinking_billed_as": "output_tokens",
        },
        {
            "provider": "gemini",
            "model": "gemini-3.1-pro-preview",
            "input_cost_per_million": 1.5,
            "output_cost_per_million": 12,
            "cached_input_cost_per_million": 0.35,
            "thinking_billed_as": "output_tokens",
        },
        # DeepSeek — PROCESSING_DEEPSEEK_MODELS
        {
            "provider": "deepseek",
            "model": "deepseek-chat",
            "input_cost_per_million": 0.27,
            "output_cost_per_million": 1.1,
        },
        {
            "provider": "deepseek",
            "model": "deepseek-vl2",
            "input_cost_per_million": 0.27,
            "output_cost_per_million": 1.1,
        },
    ],
    "aliases": [],
}
