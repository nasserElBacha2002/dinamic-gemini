"""Pricing snapshot field assembly from catalog resolution."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from src.llm.costing_helpers.catalog import PricingConfidence
from src.llm.costing_helpers.coercion import as_decimal

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PricingSnapshotBuildContext:
    """Inputs for :func:`build_pricing_snapshot_mutable` (B8.5 PLR0913)."""

    catalog: dict[str, Any]
    settings: Any
    entry: Any
    provider_norm: str
    model_norm: str | None
    n_catalog_entries: int
    raw_job_model: str | None
    canonical_model_snap: str | None
    pricing_confidence: PricingConfidence
    captured_at: str


def build_pricing_snapshot_mutable(ctx: PricingSnapshotBuildContext) -> dict[str, Any]:
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
        "captured_at": ctx.captured_at,
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
            pricing_snapshot[key] = as_decimal(ctx.entry.get(key))
        if ctx.entry.get("thinking_cost_rule") is not None:
            pricing_snapshot["thinking_cost_rule"] = (
                str(ctx.entry.get("thinking_cost_rule")).strip() or None
            )
        if ctx.entry.get("thinking_billed_as") is not None:
            pricing_snapshot["thinking_billed_as"] = (
                str(ctx.entry.get("thinking_billed_as")).strip() or None
            )
    return pricing_snapshot
