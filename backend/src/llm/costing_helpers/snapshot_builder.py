"""Orchestration for building persisted LLM cost snapshots."""

from __future__ import annotations

from collections.abc import Callable
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from src.llm.costing_helpers.billing_dimensions import apply_billable_dimensions_to_subtotals
from src.llm.costing_helpers.billing_rules import (
    dedupe_keep_order,
    derive_billing_usage_and_refine_notes,
)
from src.llm.costing_helpers.capture_status import total_cost_unavailable_reason
from src.llm.costing_helpers.catalog import (
    _pricing_confidence_for_resolution,
    load_pricing_catalog,
    resolve_pricing_with_canonical,
)
from src.llm.costing_helpers.constants import MONEY_QUANT
from src.llm.costing_helpers.formatting import (
    format_computed_cost_block,
    format_pricing_snapshot_for_json,
)
from src.llm.costing_helpers.snapshot_parts import (
    PricingSnapshotBuildContext,
    build_pricing_snapshot_mutable,
)
from src.llm.costing_helpers.usage_normalize import normalize_usage

_USAGE_METADATA_KEYS: tuple[str, ...] = (
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "cached_input_tokens",
    "cache_write_tokens",
    "thinking_tokens",
    "tool_requests",
    "image_input_count",
    "image_input_tokens",
    "audio_input_tokens",
    "video_input_tokens",
)


def _has_usage_metadata(usage: dict[str, Any]) -> bool:
    return any(usage.get(key) is not None for key in _USAGE_METADATA_KEYS)


def build_llm_cost_snapshot_impl(
    *,
    provider: str,
    model: str | None,
    raw_usage: dict[str, Any] | None,
    settings: Any,
    captured_at_factory: Callable[[], str],
) -> dict[str, Any]:
    """
    Build the auditable usage + pricing + computed-cost snapshot for one LLM call.

    ``capture_status``:
    - ``unavailable``: no usage metadata, or no monetary subtotals can be derived.
    - ``partial``: at least one billable dimension was priced but another positive usage dimension
      lacks a catalog rate (``partial_total_cost`` sums priced lines only; ``total_cost`` is null).
    - ``estimated``: every positive billable dimension has a rate and ``total_cost`` is set, but
      ``usage_dimension_ambiguous:*`` or ``usage_assumption:*`` notes remain.
    - ``exact``: operator-approved catalog row matched, full pricing coverage for positive billable
      usage, no ambiguity or assumption notes, and ``total_cost`` is set.
    """
    provider_norm = (provider or "").strip().lower() or "unknown"
    model_norm = (model or "").strip() or None
    usage, convention_notes = normalize_usage(provider_norm, raw_usage)

    catalog = load_pricing_catalog(settings)
    resolution = resolve_pricing_with_canonical(catalog, provider_norm, model_norm or "")
    entry = resolution.entry
    canonical_snap = resolution.canonical_model
    pricing_confidence = _pricing_confidence_for_resolution(catalog, resolution)

    entries_list = catalog.get("entries")
    n_catalog_entries = len(entries_list) if isinstance(entries_list, list) else 0
    pricing_snapshot = build_pricing_snapshot_mutable(
        PricingSnapshotBuildContext(
            catalog=catalog,
            settings=settings,
            entry=entry,
            provider_norm=provider_norm,
            model_norm=model_norm,
            n_catalog_entries=n_catalog_entries,
            raw_job_model=model_norm,
            canonical_model_snap=canonical_snap,
            pricing_confidence=pricing_confidence,
            captured_at=captured_at_factory(),
        )
    )

    subtotals: dict[str, Decimal | None] = {
        "subtotal_input": None,
        "subtotal_output": None,
        "subtotal_cached": None,
        "subtotal_cache_write": None,
        "subtotal_thinking": None,
        "subtotal_tools": None,
        "subtotal_image": None,
        "subtotal_audio": None,
        "subtotal_video": None,
    }

    has_usage_metadata = _has_usage_metadata(usage)
    notes: list[str] = list(convention_notes)

    billing_usage = derive_billing_usage_and_refine_notes(provider_norm, usage, entry, notes)

    has_billable_usage_signal, unpriced_dimension_present = apply_billable_dimensions_to_subtotals(
        billing_usage,
        pricing_snapshot,
        subtotals,
        notes,
    )

    subtotal_values = [v for v in subtotals.values() if v is not None]
    partial_total: Decimal | None = None
    if subtotal_values:
        partial_total = sum(subtotal_values, Decimal("0")).quantize(
            MONEY_QUANT, rounding=ROUND_HALF_UP
        )

    has_missing_pricing = any(n.startswith("billable_dimension_not_priced:") for n in notes)
    has_pricing_row = isinstance(entry, dict)
    total_cost: Decimal | None = None
    if has_pricing_row and not has_missing_pricing and subtotal_values:
        total_cost = partial_total
    elif has_pricing_row and not has_missing_pricing and not subtotal_values:
        total_cost = None

    if not has_usage_metadata:
        notes.append("provider_usage_missing")
    if not isinstance(entry, dict):
        raw_disp = model_norm or ""
        canon_disp = canonical_snap or "none"
        if resolution.alias_resolved_without_entry:
            notes.append(
                f"canonical_model_without_catalog_entry:provider={provider_norm},model={raw_disp},canonical_model={canon_disp}"
            )
        else:
            notes.append(
                f"pricing_entry_missing:provider={provider_norm},model={raw_disp},canonical_model={canon_disp}"
            )
    has_billable_not_priced_note = any(
        n.startswith("billable_dimension_not_priced:") for n in notes
    )
    if (
        isinstance(entry, dict)
        and has_billable_usage_signal
        and not subtotal_values
        and not unpriced_dimension_present
        and not has_billable_not_priced_note
    ):
        notes.append("pricing_present_but_no_billable_dimensions")

    notes = dedupe_keep_order(notes)
    if pricing_confidence == "embedded_placeholder" and total_cost is not None:
        notes.append("usage_assumption:embedded_pricing_placeholder_not_finance_approved")
    notes = dedupe_keep_order(notes)
    pricing_available = has_pricing_row
    has_dim_ambiguous = any(note.startswith("usage_dimension_ambiguous:") for note in notes)
    has_assumption = any(note.startswith("usage_assumption:") for note in notes)

    partial_total_for_json: Decimal | None = None
    if has_missing_pricing and partial_total is not None and total_cost is None:
        partial_total_for_json = partial_total

    if not has_usage_metadata:
        capture_status = "unavailable"
    elif total_cost is not None:
        if has_dim_ambiguous or has_assumption or pricing_confidence != "operator_approved":
            capture_status = "estimated"
        else:
            capture_status = "exact"
    elif partial_total_for_json is not None:
        capture_status = "partial"
    else:
        capture_status = "unavailable"

    unavailable_reason = total_cost_unavailable_reason(
        total_cost=total_cost,
        partial_total_cost=partial_total_for_json,
        notes=notes,
        ambiguous=has_dim_ambiguous,
        has_usage_metadata=has_usage_metadata,
    )

    return {
        "provider": provider_norm,
        "model": model_norm,
        "canonical_model": canonical_snap,
        "pricing_available": pricing_available,
        "billing_currency": pricing_snapshot["billing_currency"],
        "usage": usage,
        "pricing_snapshot": format_pricing_snapshot_for_json(pricing_snapshot),
        "computed_cost": format_computed_cost_block(
            subtotals,
            total_cost=total_cost,
            partial_total_cost=partial_total_for_json,
            billing_currency=pricing_snapshot["billing_currency"],
            total_cost_unavailable_reason=unavailable_reason,
        ),
        "capture_status": capture_status,
        "capture_notes": notes,
    }
