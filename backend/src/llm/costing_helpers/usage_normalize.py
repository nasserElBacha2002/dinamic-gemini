"""Provider-agnostic LLM usage field normalization."""

from __future__ import annotations

from typing import Any

from src.llm.costing_helpers.coercion import get_first, to_int


def _apply_openai_input_and_cache_conventions(
    usage: dict[str, Any], raw: dict[str, Any], notes: list[str]
) -> None:
    """Mutates ``usage`` / ``notes`` for OpenAI provider keys (no formula change)."""
    prompt_tokens = get_first(raw, "prompt_tokens")
    cached = usage["cached_input_tokens"]
    if prompt_tokens is not None and cached is not None:
        usage["input_tokens"] = max(0, prompt_tokens - cached)
        usage["cached_input_tokens"] = cached
    elif prompt_tokens is not None:
        usage["input_tokens"] = prompt_tokens
        notes.append("usage_dimension_ambiguous:cached_input")


def _apply_gemini_input_and_ambiguity_notes(
    usage: dict[str, Any], raw: dict[str, Any], notes: list[str]
) -> None:
    prompt_tokens = get_first(raw, "prompt_token_count")
    cached = get_first(raw, "cached_content_token_count")
    if prompt_tokens is not None and cached is not None:
        usage["input_tokens"] = max(0, prompt_tokens - cached)
        usage["cached_input_tokens"] = cached
    elif prompt_tokens is not None:
        usage["input_tokens"] = prompt_tokens
        if prompt_tokens > 0:
            notes.append("usage_dimension_ambiguous:cached_input")

    cand = get_first(raw, "candidates_token_count")
    thoughts = get_first(raw, "thoughts_token_count")
    if cand is not None and thoughts is not None and thoughts > 0:
        notes.append("usage_dimension_ambiguous:output_tokens")


def _apply_claude_cache_conventions(
    usage: dict[str, Any], raw: dict[str, Any], notes: list[str]
) -> None:
    """Map Anthropic usage into billable dimensions.

    Anthropic reports ``input_tokens`` (non-cache prompt) alongside ``cache_read_input_tokens``
    (cache hits). We treat them as non-overlapping billable buckets when both are present and
    record an explicit assumption note (does not block cost totals).
    """
    inp = get_first(raw, "input_tokens")
    cache_read = get_first(raw, "cache_read_input_tokens")
    cache_write = get_first(raw, "cache_creation_input_tokens")
    if cache_write is not None:
        usage["cache_write_tokens"] = cache_write
    if inp is not None:
        usage["input_tokens"] = inp
    if cache_read is not None:
        usage["cached_input_tokens"] = cache_read
    if inp is not None and cache_read is not None and inp > 0 and cache_read > 0:
        notes.append("usage_assumption:claude_input_tokens_non_cache_or_provider_reported")


def normalize_usage(
    provider: str, raw_usage: dict[str, Any] | None
) -> tuple[dict[str, Any], list[str]]:
    """
    Normalize known token/usage fields into a provider-agnostic structure.

    Returns ``(usage, convention_notes)`` where notes capture ambiguities that should downgrade
    confidence (``capture_status``).

    IMPORTANT: ``total_tokens`` is conservative and provider-native only; we do not derive it.
    """
    notes: list[str] = []
    raw = dict(raw_usage or {})
    p = (provider or "").strip().lower() or "unknown"

    usage: dict[str, Any] = {
        "input_tokens": get_first(
            raw, "input_tokens", "prompt_tokens", "input_token_count", "prompt_token_count"
        ),
        "output_tokens": get_first(
            raw,
            "output_tokens",
            "completion_tokens",
            "candidates_token_count",
            "output_token_count",
        ),
        "total_tokens": get_first(raw, "total_tokens", "total_token_count"),
        "cached_input_tokens": get_first(
            raw,
            "cached_input_tokens",
            "cached_tokens",
            "cached_content_token_count",
            "cache_read_input_tokens",
        ),
        "cache_write_tokens": get_first(raw, "cache_write_tokens", "cache_creation_input_tokens"),
        "thinking_tokens": get_first(
            raw, "thinking_tokens", "thoughts_token_count", "reasoning_tokens"
        ),
        "tool_requests": get_first(raw, "tool_requests"),
        "image_input_count": get_first(raw, "image_input_count", "image_count"),
        "image_input_tokens": get_first(raw, "image_input_tokens"),
        "audio_input_tokens": get_first(raw, "audio_input_tokens"),
        "video_input_tokens": get_first(raw, "video_input_tokens"),
        "raw_provider_usage_json": raw,
    }

    # OpenAI nested details
    input_details = raw.get("input_tokens_details") or raw.get("prompt_tokens_details")
    if isinstance(input_details, dict) and usage["cached_input_tokens"] is None:
        usage["cached_input_tokens"] = to_int(input_details.get("cached_tokens"))
    output_details = raw.get("output_tokens_details") or raw.get("completion_tokens_details")
    if isinstance(output_details, dict) and usage["thinking_tokens"] is None:
        usage["thinking_tokens"] = to_int(output_details.get("reasoning_tokens"))
    if usage["tool_requests"] is None and isinstance(raw.get("tool_calls"), list):
        usage["tool_requests"] = len(raw["tool_calls"])

    # Provider-specific conventions
    if p == "openai":
        _apply_openai_input_and_cache_conventions(usage, raw, notes)
    elif p == "gemini":
        _apply_gemini_input_and_ambiguity_notes(usage, raw, notes)
    elif p == "claude":
        _apply_claude_cache_conventions(usage, raw, notes)

    if (
        usage["total_tokens"] is not None
        and usage["input_tokens"] is None
        and usage["output_tokens"] is None
        and usage["thinking_tokens"] is None
    ):
        notes.append("usage_dimension_ambiguous:input_tokens")

    return usage, notes
