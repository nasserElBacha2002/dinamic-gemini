"""Pure billing calculators for LLM cost snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Literal

from src.llm.costing_helpers.coercion import usage_int
from src.llm.costing_helpers.constants import MICRO_UNIT, MONEY_QUANT


def compute_per_million(tokens: int, per_million: Decimal) -> Decimal:
    return (Decimal(tokens) * per_million / MICRO_UNIT).quantize(
        MONEY_QUANT, rounding=ROUND_HALF_UP
    )


def compute_unit(units: int, unit_cost: Decimal) -> Decimal:
    return (Decimal(units) * unit_cost).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class BillableDimension:
    usage_key: str
    pricing_key: str | None
    subtotal_key: str | None
    mode: Literal["per_million", "unit", "unpriced"]


BILLABLE_DIMENSIONS: tuple[BillableDimension, ...] = (
    BillableDimension("input_tokens", "input_cost_per_million", "subtotal_input", "per_million"),
    BillableDimension("output_tokens", "output_cost_per_million", "subtotal_output", "per_million"),
    BillableDimension(
        "cached_input_tokens", "cached_input_cost_per_million", "subtotal_cached", "per_million"
    ),
    BillableDimension(
        "thinking_tokens", "thinking_cost_per_million", "subtotal_thinking", "per_million"
    ),
    BillableDimension("tool_requests", "tool_request_unit_cost", "subtotal_tools", "unit"),
    BillableDimension("image_input_count", "image_input_unit_cost", "subtotal_image", "unit"),
    BillableDimension(
        "audio_input_tokens", "audio_input_cost_per_million", "subtotal_audio", "per_million"
    ),
    BillableDimension(
        "video_input_tokens", "video_input_cost_per_million", "subtotal_video", "per_million"
    ),
    BillableDimension(
        "cache_write_tokens",
        "cache_write_cost_per_million",
        "subtotal_cache_write",
        "per_million",
    ),
    BillableDimension("image_input_tokens", None, None, "unpriced"),
)


def apply_billable_dimensions_to_subtotals(
    usage: dict[str, Any],
    pricing_snapshot: dict[str, Any],
    subtotals: dict[str, Decimal | None],
    notes: list[str],
) -> tuple[bool, bool]:
    """Accumulate billable dimensions into ``subtotals`` and ``notes`` (mutating). No formula changes."""
    has_billable_usage_signal = False
    unpriced_dimension_present = False
    for dim in BILLABLE_DIMENSIONS:
        amount = usage_int(usage, dim.usage_key)
        if amount is None:
            continue
        if amount > 0:
            has_billable_usage_signal = True

        if dim.mode == "unpriced":
            if amount is not None and amount > 0:
                unpriced_dimension_present = True
                notes.append(f"billable_dimension_not_priced:{dim.usage_key}")
            continue

        if dim.pricing_key is None or dim.subtotal_key is None:
            continue
        price = pricing_snapshot.get(dim.pricing_key)
        if price is None:
            if amount > 0:
                notes.append(f"billable_dimension_not_priced:{dim.usage_key}")
            continue

        assert isinstance(price, Decimal)
        if dim.mode == "per_million":
            subtotals[dim.subtotal_key] = compute_per_million(amount, price)
        elif dim.mode == "unit":
            subtotals[dim.subtotal_key] = compute_unit(amount, price)
    return has_billable_usage_signal, unpriced_dimension_present
