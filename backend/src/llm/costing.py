"""
Provider-agnostic LLM usage/cost snapshot builder.

The snapshot is persisted with each run for auditability. To avoid overclaiming precision:
- ``total_tokens`` is kept only when reported by the provider payload.
- ambiguous accounting paths are explicitly marked with ``usage_dimension_ambiguous:*`` notes.
- ``pricing_snapshot.pricing_confidence`` distinguishes operator-approved catalog rows from embedded placeholders.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from src.llm.costing_helpers.billing_dimensions import (
    apply_billable_dimensions_to_subtotals as _apply_billable_dimensions_to_subtotals,
)
from src.llm.costing_helpers.billing_rules import (
    _dedupe_keep_order,
)
from src.llm.costing_helpers.billing_rules import (
    derive_billing_usage_and_refine_notes as _derive_billing_usage_and_refine_notes,
)
from src.llm.costing_helpers.catalog import (
    PricingConfidence as _PricingConfidence,
)
from src.llm.costing_helpers.catalog import (
    _pricing_confidence_for_resolution,
    resolve_pricing_with_canonical,
)
from src.llm.costing_helpers.catalog import (
    load_pricing_catalog as _load_pricing_catalog,
)
from src.llm.costing_helpers.coercion import as_decimal as _as_decimal
from src.llm.costing_helpers.constants import MONEY_QUANT as _MONEY_QUANT
from src.llm.costing_helpers.formatting import (
    format_computed_cost_block as _format_computed_cost_block,
)
from src.llm.costing_helpers.formatting import (
    format_pricing_snapshot_for_json as _format_pricing_snapshot_for_json,
)
from src.llm.costing_helpers.usage_normalize import normalize_usage

logger = logging.getLogger(__name__)


def _utc_iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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


@dataclass(frozen=True)
class _PricingSnapshotBuildContext:
    """Inputs for :func:`_build_pricing_snapshot_mutable` (B8.5 PLR0913)."""

    catalog: dict[str, Any]
    settings: Any
    entry: Any
    provider_norm: str
    model_norm: str | None
    n_catalog_entries: int
    raw_job_model: str | None
    canonical_model_snap: str | None
    pricing_confidence: _PricingConfidence


def _build_pricing_snapshot_mutable(ctx: _PricingSnapshotBuildContext) -> dict[str, Any]:
    """Assemble rate fields merged from catalog entry (logic unchanged from inline block)."""
    if not isinstance(ctx.entry, dict):
        logger.info(
            "llm.pricing_entry_missing provider=%s model=%r catalog_entries=%d",
            ctx.provider_norm,
            ctx.model_norm,
            ctx.n_catalog_entries,
        )

    catalog_currency = (
        ctx.catalog.get("currency") if isinstance(ctx.catalog.get("currency"), str) else None
    ) or "USD"
    pricing_version = (
        (ctx.catalog.get("version") if isinstance(ctx.catalog.get("version"), str) else None)
        or (getattr(ctx.settings, "llm_pricing_catalog_version", "") or "").strip()
        or None
    )
    pricing_source = (
        ctx.catalog.get("source") if isinstance(ctx.catalog.get("source"), str) else None
    ) or "settings.llm_pricing_catalog_json"
    catalog_entry_captured_at = (
        str(ctx.entry.get("captured_at")).strip()
        if isinstance(ctx.entry, dict)
        and ctx.entry.get("captured_at") is not None
        and str(ctx.entry.get("captured_at")).strip()
        else None
    )

    raw_model_disp = (ctx.raw_job_model or "").strip() or None
    canon_disp = (ctx.canonical_model_snap or "").strip() or None

    pricing_snapshot: dict[str, Any] = {
        "pricing_source": pricing_source,
        "pricing_version": pricing_version,
        "captured_at": _utc_iso_now(),
        "pricing_catalog_entry_captured_at": catalog_entry_captured_at,
        "billing_currency": catalog_currency,
        "price_units": "per_1m_tokens",
        "provider": ctx.provider_norm,
        "model": raw_model_disp,
        "canonical_model": canon_disp,
        "input_cost_per_million": None,
        "output_cost_per_million": None,
        "cached_input_cost_per_million": None,
        "thinking_cost_per_million": None,
        "cache_write_cost_per_million": None,
        "tool_request_unit_cost": None,
        "image_input_unit_cost": None,
        "audio_input_cost_per_million": None,
        "video_input_cost_per_million": None,
        "thinking_cost_rule": None,
        "thinking_billed_as": None,
        "pricing_confidence": ctx.pricing_confidence,
    }

    if isinstance(ctx.entry, dict):
        currency_raw = ctx.entry.get("currency")
        if isinstance(currency_raw, str) and currency_raw.strip():
            pricing_snapshot["billing_currency"] = currency_raw.strip()
        for key in (
            "input_cost_per_million",
            "output_cost_per_million",
            "cached_input_cost_per_million",
            "thinking_cost_per_million",
            "cache_write_cost_per_million",
            "tool_request_unit_cost",
            "image_input_unit_cost",
            "audio_input_cost_per_million",
            "video_input_cost_per_million",
        ):
            pricing_snapshot[key] = _as_decimal(ctx.entry.get(key))
        if ctx.entry.get("thinking_cost_rule") is not None:
            pricing_snapshot["thinking_cost_rule"] = (
                str(ctx.entry.get("thinking_cost_rule")).strip() or None
            )
        if ctx.entry.get("thinking_billed_as") is not None:
            pricing_snapshot["thinking_billed_as"] = (
                str(ctx.entry.get("thinking_billed_as")).strip() or None
            )
    return pricing_snapshot


def _total_cost_unavailable_reason(
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


def build_llm_cost_snapshot(
    *,
    provider: str,
    model: str | None,
    raw_usage: dict[str, Any] | None,
    settings: Any,
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

    catalog = _load_pricing_catalog(settings)
    resolution = resolve_pricing_with_canonical(catalog, provider_norm, model_norm or "")
    entry = resolution.entry
    canonical_snap = resolution.canonical_model
    pricing_confidence = _pricing_confidence_for_resolution(catalog, resolution)

    entries_list = catalog.get("entries")
    n_catalog_entries = len(entries_list) if isinstance(entries_list, list) else 0
    pricing_snapshot = _build_pricing_snapshot_mutable(
        _PricingSnapshotBuildContext(
            catalog=catalog,
            settings=settings,
            entry=entry,
            provider_norm=provider_norm,
            model_norm=model_norm,
            n_catalog_entries=n_catalog_entries,
            raw_job_model=model_norm,
            canonical_model_snap=canonical_snap,
            pricing_confidence=pricing_confidence,
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

    billing_usage = _derive_billing_usage_and_refine_notes(provider_norm, usage, entry, notes)

    has_billable_usage_signal, unpriced_dimension_present = _apply_billable_dimensions_to_subtotals(
        billing_usage,
        pricing_snapshot,
        subtotals,
        notes,
    )

    subtotal_values = [v for v in subtotals.values() if v is not None]
    partial_total: Decimal | None = None
    if subtotal_values:
        partial_total = sum(subtotal_values, Decimal("0")).quantize(
            _MONEY_QUANT, rounding=ROUND_HALF_UP
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

    notes = _dedupe_keep_order(notes)
    if pricing_confidence == "embedded_placeholder" and total_cost is not None:
        notes.append("usage_assumption:embedded_pricing_placeholder_not_finance_approved")
    notes = _dedupe_keep_order(notes)
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

    total_cost_unavailable_reason = _total_cost_unavailable_reason(
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
        "pricing_snapshot": _format_pricing_snapshot_for_json(pricing_snapshot),
        "computed_cost": _format_computed_cost_block(
            subtotals,
            total_cost=total_cost,
            partial_total_cost=partial_total_for_json,
            billing_currency=pricing_snapshot["billing_currency"],
            total_cost_unavailable_reason=total_cost_unavailable_reason,
        ),
        "capture_status": capture_status,
        "capture_notes": notes,
    }


def _split_csv_models(raw: str) -> list[str]:
    return [p.strip() for p in (raw or "").split(",") if p.strip()]


@dataclass(frozen=True)
class PricingCoverageIssue:
    """One configured model string checked against the merged pricing catalog."""

    provider: str
    raw_model: str
    canonical_model: str | None
    has_entry: bool
    missing_reason: str


def validate_llm_pricing_coverage(settings: Any) -> list[PricingCoverageIssue]:
    """Read-only: compare operator processing model lists with merged catalog coverage."""
    catalog = _load_pricing_catalog(settings)
    pairs: list[tuple[str, str]] = []
    for m in _split_csv_models(getattr(settings, "processing_claude_models", "") or ""):
        pairs.append(("claude", m))
    for m in _split_csv_models(getattr(settings, "processing_gemini_models", "") or ""):
        pairs.append(("gemini", m))
    for m in _split_csv_models(getattr(settings, "processing_openai_models", "") or ""):
        pairs.append(("openai", m))
    for attr, prov in (
        ("anthropic_model", "claude"),
        ("gemini_model_name", "gemini"),
        ("openai_model", "openai"),
    ):
        v = getattr(settings, attr, None)
        if isinstance(v, str) and v.strip():
            pairs.append((prov, v.strip()))

    seen: set[tuple[str, str]] = set()
    out: list[PricingCoverageIssue] = []
    for provider, raw in pairs:
        key = (provider.lower(), raw.lower())
        if key in seen:
            continue
        seen.add(key)
        res = resolve_pricing_with_canonical(catalog, provider, raw)
        has_entry = isinstance(res.entry, dict)
        if has_entry:
            out.append(
                PricingCoverageIssue(
                    provider=provider,
                    raw_model=raw,
                    canonical_model=res.canonical_model,
                    has_entry=True,
                    missing_reason="",
                )
            )
            continue
        if res.alias_resolved_without_entry:
            reason = "canonical_model_without_catalog_entry"
        else:
            reason = "pricing_entry_missing"
        out.append(
            PricingCoverageIssue(
                provider=provider,
                raw_model=raw,
                canonical_model=res.canonical_model,
                has_entry=False,
                missing_reason=reason,
            )
        )
    return out
