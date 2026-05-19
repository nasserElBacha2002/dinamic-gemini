"""Capture-status unavailable-reason resolution for LLM cost snapshots."""

from __future__ import annotations

from decimal import Decimal


def total_cost_unavailable_reason(
    *,
    total_cost: Decimal | None,
    partial_total_cost: Decimal | None,
    notes: list[str],
    ambiguous: bool,
    has_usage_metadata: bool,
) -> str | None:
    """Mirror legacy elif ladder for ``total_cost_unavailable_reason`` (single exit)."""
    if total_cost is not None:
        return None
    reason: str | None = None
    if "provider_usage_missing" in notes:
        reason = "provider_usage_missing"
    elif any(
        n == "canonical_model_without_catalog_entry"
        or n.startswith("canonical_model_without_catalog_entry:")
        for n in notes
    ):
        reason = "canonical_model_without_catalog_entry"
    elif any(n == "pricing_entry_missing" or n.startswith("pricing_entry_missing:") for n in notes):
        reason = "pricing_entry_missing"
    elif partial_total_cost is not None:
        reason = "billable_dimension_not_priced"
    elif any(n.startswith("billable_dimension_not_priced:") for n in notes):
        reason = "billable_dimension_not_priced"
    elif "pricing_present_but_no_billable_dimensions" in notes:
        reason = "pricing_present_but_no_billable_dimensions"
    elif ambiguous:
        reason = "usage_dimension_ambiguous"
    elif has_usage_metadata:
        reason = "cost_not_computed"
    return reason
