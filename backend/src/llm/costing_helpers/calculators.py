"""Pure billing calculators for LLM cost snapshots."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from src.llm.costing_helpers.constants import MICRO_UNIT, MONEY_QUANT


def compute_per_million(tokens: int, per_million: Decimal) -> Decimal:
    return (Decimal(tokens) * per_million / MICRO_UNIT).quantize(
        MONEY_QUANT, rounding=ROUND_HALF_UP
    )


def compute_unit(units: int, unit_cost: Decimal) -> Decimal:
    return (Decimal(units) * unit_cost).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)
