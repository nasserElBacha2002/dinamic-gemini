"""Provider/catalog billing usage adjustments and capture note helpers."""

from __future__ import annotations

from typing import Any

from src.llm.costing_helpers.coercion import as_decimal, to_int


def dedupe_keep_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def _strip_notes_with_prefix(notes: list[str], prefix: str) -> None:
    """Remove notes starting with ``prefix`` (mutating, stable order)."""
    del_idxs = [i for i, n in enumerate(notes) if n.startswith(prefix)]
    for i in reversed(del_idxs):
        notes.pop(i)


def derive_billing_usage_and_refine_notes(
    provider_norm: str,
    usage: dict[str, Any],
    entry: Any,
    notes: list[str],
) -> dict[str, Any]:
    """Shallow billing copy + provider/catalog policies (does not mutate ``usage``)."""
    billing = {k: usage[k] for k in usage if k != "raw_provider_usage_json"}
    if not isinstance(entry, dict):
        return billing

    if provider_norm == "gemini":
        tb = str(entry.get("thinking_billed_as") or "").strip().lower()
        has_thinking_price = as_decimal(entry.get("thinking_cost_per_million")) is not None
        if tb == "output_tokens":
            o = to_int(billing.get("output_tokens")) or 0
            th = to_int(billing.get("thinking_tokens")) or 0
            billing["output_tokens"] = o + th
            billing["thinking_tokens"] = 0
            _strip_notes_with_prefix(notes, "usage_dimension_ambiguous:output_tokens")
        elif has_thinking_price:
            _strip_notes_with_prefix(notes, "usage_dimension_ambiguous:output_tokens")

    if provider_norm == "openai":
        out_t = to_int(billing.get("output_tokens"))
        think_t = to_int(billing.get("thinking_tokens"))
        if think_t is not None and think_t > 0 and out_t is not None and think_t <= out_t:
            billing["thinking_tokens"] = 0
            notes.append("usage_assumption:openai_reasoning_tokens_subsumed_by_completion")

    return billing
