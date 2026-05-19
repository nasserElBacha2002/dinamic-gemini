"""Pricing catalog coverage validation for configured processing models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.llm.costing_helpers.catalog import load_pricing_catalog, resolve_pricing_with_canonical


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
    catalog = load_pricing_catalog(settings)
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
