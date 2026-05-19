"""
Provider-agnostic LLM usage/cost snapshot builder.

The snapshot is persisted with each run for auditability. To avoid overclaiming precision:
- ``total_tokens`` is kept only when reported by the provider payload.
- ambiguous accounting paths are explicitly marked with ``usage_dimension_ambiguous:*`` notes.
- ``pricing_snapshot.pricing_confidence`` distinguishes operator-approved catalog rows from embedded placeholders.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from src.llm.costing_helpers.capture_status import (
    total_cost_unavailable_reason as _total_cost_unavailable_reason,  # noqa: F401
)
from src.llm.costing_helpers.catalog import (
    load_pricing_catalog as _load_pricing_catalog,
    resolve_pricing_with_canonical,
)
from src.llm.costing_helpers.snapshot_builder import build_llm_cost_snapshot_impl
from src.llm.costing_helpers.usage_normalize import normalize_usage

__all__ = [
    "PricingCoverageIssue",
    "build_llm_cost_snapshot",
    "normalize_usage",
    "resolve_pricing_with_canonical",
    "validate_llm_pricing_coverage",
]


def _utc_iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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
    return build_llm_cost_snapshot_impl(
        provider=provider,
        model=model,
        raw_usage=raw_usage,
        settings=settings,
        captured_at_factory=_utc_iso_now,
    )


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
