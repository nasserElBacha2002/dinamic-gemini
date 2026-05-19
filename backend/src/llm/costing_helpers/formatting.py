"""Money and snapshot block formatting for persisted LLM cost snapshots."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from src.llm.costing_helpers.constants import MONEY_QUANT


def format_money_optional(value: Decimal | None) -> str | None:
    """Serialize money-like Decimals as fixed-point strings (avoids ``0E-8`` style output)."""
    if value is None:
        return None
    q = value.quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)
    return format(q, "f")


def format_pricing_snapshot_for_json(pricing_snapshot: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "input_cost_per_million",
        "output_cost_per_million",
        "cached_input_cost_per_million",
        "thinking_cost_per_million",
        "cache_write_cost_per_million",
        "tool_request_unit_cost",
        "image_input_unit_cost",
        "audio_input_cost_per_million",
        "video_input_cost_per_million",
    )
    formatted = {k: format_money_optional(pricing_snapshot[k]) for k in keys}
    return {**pricing_snapshot, **formatted}


def format_computed_cost_block(
    subtotals: dict[str, Decimal | None],
    *,
    total_cost: Decimal | None,
    partial_total_cost: Decimal | None,
    billing_currency: str,
    total_cost_unavailable_reason: str | None,
) -> dict[str, Any]:
    return {
        "subtotal_input": format_money_optional(subtotals["subtotal_input"]),
        "subtotal_output": format_money_optional(subtotals["subtotal_output"]),
        "subtotal_cached": format_money_optional(subtotals["subtotal_cached"]),
        "subtotal_cache_write": format_money_optional(subtotals.get("subtotal_cache_write")),
        "subtotal_thinking": format_money_optional(subtotals["subtotal_thinking"]),
        "subtotal_tools": format_money_optional(subtotals["subtotal_tools"]),
        "subtotal_image": format_money_optional(subtotals["subtotal_image"]),
        "subtotal_audio": format_money_optional(subtotals["subtotal_audio"]),
        "subtotal_video": format_money_optional(subtotals["subtotal_video"]),
        "partial_total_cost": format_money_optional(partial_total_cost),
        "total_cost": format_money_optional(total_cost),
        "currency": billing_currency,
        "total_cost_unavailable_reason": total_cost_unavailable_reason,
    }
