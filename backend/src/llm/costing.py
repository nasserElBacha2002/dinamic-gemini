"""
Provider-agnostic LLM usage/cost snapshot builder.

The snapshot is persisted with each run for auditability. To avoid overclaiming precision:
- ``total_tokens`` is kept only when reported by the provider payload.
- ambiguous accounting paths are explicitly marked with ``usage_dimension_ambiguous:*`` notes.
- ``pricing_snapshot.pricing_confidence`` distinguishes operator-approved catalog rows from embedded placeholders.
"""

from __future__ import annotations

import copy
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Literal

from src.llm.costing_helpers.calculators import (
    apply_billable_dimensions_to_subtotals as _apply_billable_dimensions_to_subtotals,
)
from src.llm.costing_helpers.coercion import as_decimal as _as_decimal
from src.llm.costing_helpers.coercion import get_first as _get_first
from src.llm.costing_helpers.coercion import to_int as _to_int
from src.llm.costing_helpers.constants import MONEY_QUANT as _MONEY_QUANT
from src.llm.costing_helpers.formatting import (
    format_computed_cost_block as _format_computed_cost_block,
)
from src.llm.costing_helpers.formatting import (
    format_pricing_snapshot_for_json as _format_pricing_snapshot_for_json,
)

_PricingConfidence = Literal["operator_approved", "embedded_placeholder", "unknown"]

logger = logging.getLogger(__name__)

# Merged under operator JSON (``LLM_PRICING_CATALOG_JSON``); user entries override on same
# (provider, model) keys. USD values are deployment placeholders — override via env JSON for
# finance-approved list prices. Shape must match ``_load_pricing_catalog``: ``entries`` +
# optional ``aliases`` (see H7).
_EMBEDDED_DEFAULT_LLM_PRICING_CATALOG: dict[str, Any] = {
    "version": "dinamic-embedded-pricing-v2",
    "currency": "USD",
    "source": "dinamic_embedded_placeholders",
    "entries": [
        # OpenAI — aligned with typical PROCESSING_OPENAI_MODELS / OPENAI_MODEL
        {
            "provider": "openai",
            "model": "gpt-5.5",
            "input_cost_per_million": 5,
            "output_cost_per_million": 15,
            "cached_input_cost_per_million": 1.25,
        },
        {
            "provider": "openai",
            "model": "gpt-5.4",
            "input_cost_per_million": 5,
            "output_cost_per_million": 15,
            "cached_input_cost_per_million": 1.25,
        },
        {
            "provider": "openai",
            "model": "gpt-5.4-mini",
            "input_cost_per_million": 0.8,
            "output_cost_per_million": 2.4,
            "cached_input_cost_per_million": 0.16,
        },
        {
            "provider": "openai",
            "model": "gpt-5.4-nano",
            "input_cost_per_million": 0.2,
            "output_cost_per_million": 0.6,
            "cached_input_cost_per_million": 0.04,
        },
        {
            "provider": "openai",
            "model": "gpt-4o",
            "input_cost_per_million": 5,
            "output_cost_per_million": 15,
            "cached_input_cost_per_million": 1.25,
        },
        {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "input_cost_per_million": 0.15,
            "output_cost_per_million": 0.6,
            "cached_input_cost_per_million": 0.075,
        },
        {
            "provider": "openai",
            "model": "gpt-4-turbo",
            "input_cost_per_million": 10,
            "output_cost_per_million": 30,
            "cached_input_cost_per_million": 2.5,
        },
        # Anthropic — PROCESSING_CLAUDE_MODELS + ANTHROPIC_MODEL default
        {
            "provider": "claude",
            "model": "claude-sonnet-4-20250514",
            "input_cost_per_million": 3,
            "output_cost_per_million": 15,
            "cached_input_cost_per_million": 1,
        },
        {
            "provider": "claude",
            "model": "claude-3-5-sonnet-20241022",
            "input_cost_per_million": 3,
            "output_cost_per_million": 15,
            "cached_input_cost_per_million": 1,
        },
        {
            "provider": "claude",
            "model": "claude-opus-4-7",
            "input_cost_per_million": 15,
            "output_cost_per_million": 75,
            "cached_input_cost_per_million": 7.5,
        },
        {
            "provider": "claude",
            "model": "claude-sonnet-4-6",
            "input_cost_per_million": 3,
            "output_cost_per_million": 15,
            "cached_input_cost_per_million": 1,
        },
        {
            "provider": "claude",
            "model": "claude-haiku-4-5-20251001",
            "input_cost_per_million": 1,
            "output_cost_per_million": 5,
            "cached_input_cost_per_million": 0.5,
        },
        # Gemini — PROCESSING_GEMINI_MODELS / GEMINI_MODEL_NAME (thinking billed as output)
        {
            "provider": "gemini",
            "model": "gemini-2.5-pro",
            "input_cost_per_million": 1.25,
            "output_cost_per_million": 10,
            "cached_input_cost_per_million": 0.31,
            "thinking_billed_as": "output_tokens",
        },
        {
            "provider": "gemini",
            "model": "gemini-2.5-flash",
            "input_cost_per_million": 0.3,
            "output_cost_per_million": 2.5,
            "cached_input_cost_per_million": 0.08,
            "thinking_billed_as": "output_tokens",
        },
        {
            "provider": "gemini",
            "model": "gemini-3.1-flash-lite",
            "input_cost_per_million": 0.2,
            "output_cost_per_million": 0.6,
            "cached_input_cost_per_million": 0.05,
            "thinking_billed_as": "output_tokens",
        },
        {
            "provider": "gemini",
            "model": "gemini-3.1-pro-preview",
            "input_cost_per_million": 1.5,
            "output_cost_per_million": 12,
            "cached_input_cost_per_million": 0.35,
            "thinking_billed_as": "output_tokens",
        },
        # DeepSeek — PROCESSING_DEEPSEEK_MODELS
        {
            "provider": "deepseek",
            "model": "deepseek-chat",
            "input_cost_per_million": 0.27,
            "output_cost_per_million": 1.1,
        },
        {
            "provider": "deepseek",
            "model": "deepseek-vl2",
            "input_cost_per_million": 0.27,
            "output_cost_per_million": 1.1,
        },
    ],
    "aliases": [],
}


def _utc_iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _apply_openai_input_and_cache_conventions(
    usage: dict[str, Any], raw: dict[str, Any], notes: list[str]
) -> None:
    """Mutates ``usage`` / ``notes`` for OpenAI provider keys (no formula change)."""
    prompt_tokens = _get_first(raw, "prompt_tokens")
    cached = usage["cached_input_tokens"]
    if prompt_tokens is not None and cached is not None:
        usage["input_tokens"] = max(0, prompt_tokens - cached)
        usage["cached_input_tokens"] = cached
    elif prompt_tokens is not None:
        usage["input_tokens"] = prompt_tokens
        notes.append("usage_dimension_ambiguous:cached_input")


def _apply_gemini_input_and_ambiguity_notes(
    usage: dict[str, Any], raw: dict[str, Any], notes: list[str]
) -> None:
    prompt_tokens = _get_first(raw, "prompt_token_count")
    cached = _get_first(raw, "cached_content_token_count")
    if prompt_tokens is not None and cached is not None:
        usage["input_tokens"] = max(0, prompt_tokens - cached)
        usage["cached_input_tokens"] = cached
    elif prompt_tokens is not None:
        usage["input_tokens"] = prompt_tokens
        if prompt_tokens > 0:
            notes.append("usage_dimension_ambiguous:cached_input")

    cand = _get_first(raw, "candidates_token_count")
    thoughts = _get_first(raw, "thoughts_token_count")
    if cand is not None and thoughts is not None and thoughts > 0:
        notes.append("usage_dimension_ambiguous:output_tokens")


def _apply_claude_cache_conventions(
    usage: dict[str, Any], raw: dict[str, Any], notes: list[str]
) -> None:
    """Map Anthropic usage into billable dimensions.

    Anthropic reports ``input_tokens`` (non-cache prompt) alongside ``cache_read_input_tokens``
    (cache hits). We treat them as non-overlapping billable buckets when both are present and
    record an explicit assumption note (does not block cost totals).
    """
    inp = _get_first(raw, "input_tokens")
    cache_read = _get_first(raw, "cache_read_input_tokens")
    cache_write = _get_first(raw, "cache_creation_input_tokens")
    if cache_write is not None:
        usage["cache_write_tokens"] = cache_write
    if inp is not None:
        usage["input_tokens"] = inp
    if cache_read is not None:
        usage["cached_input_tokens"] = cache_read
    if inp is not None and cache_read is not None and inp > 0 and cache_read > 0:
        notes.append("usage_assumption:claude_input_tokens_non_cache_or_provider_reported")


def normalize_usage(
    provider: str, raw_usage: dict[str, Any] | None
) -> tuple[dict[str, Any], list[str]]:
    """
    Normalize known token/usage fields into a provider-agnostic structure.

    Returns ``(usage, convention_notes)`` where notes capture ambiguities that should downgrade
    confidence (``capture_status``).

    IMPORTANT: ``total_tokens`` is conservative and provider-native only; we do not derive it.
    """
    notes: list[str] = []
    raw = dict(raw_usage or {})
    p = (provider or "").strip().lower() or "unknown"

    usage: dict[str, Any] = {
        "input_tokens": _get_first(
            raw, "input_tokens", "prompt_tokens", "input_token_count", "prompt_token_count"
        ),
        "output_tokens": _get_first(
            raw,
            "output_tokens",
            "completion_tokens",
            "candidates_token_count",
            "output_token_count",
        ),
        "total_tokens": _get_first(raw, "total_tokens", "total_token_count"),
        "cached_input_tokens": _get_first(
            raw,
            "cached_input_tokens",
            "cached_tokens",
            "cached_content_token_count",
            "cache_read_input_tokens",
        ),
        "cache_write_tokens": _get_first(raw, "cache_write_tokens", "cache_creation_input_tokens"),
        "thinking_tokens": _get_first(
            raw, "thinking_tokens", "thoughts_token_count", "reasoning_tokens"
        ),
        "tool_requests": _get_first(raw, "tool_requests"),
        "image_input_count": _get_first(raw, "image_input_count", "image_count"),
        "image_input_tokens": _get_first(raw, "image_input_tokens"),
        "audio_input_tokens": _get_first(raw, "audio_input_tokens"),
        "video_input_tokens": _get_first(raw, "video_input_tokens"),
        "raw_provider_usage_json": raw,
    }

    # OpenAI nested details
    input_details = raw.get("input_tokens_details") or raw.get("prompt_tokens_details")
    if isinstance(input_details, dict) and usage["cached_input_tokens"] is None:
        usage["cached_input_tokens"] = _to_int(input_details.get("cached_tokens"))
    output_details = raw.get("output_tokens_details") or raw.get("completion_tokens_details")
    if isinstance(output_details, dict) and usage["thinking_tokens"] is None:
        usage["thinking_tokens"] = _to_int(output_details.get("reasoning_tokens"))
    if usage["tool_requests"] is None and isinstance(raw.get("tool_calls"), list):
        usage["tool_requests"] = len(raw["tool_calls"])

    # Provider-specific conventions
    if p == "openai":
        _apply_openai_input_and_cache_conventions(usage, raw, notes)
    elif p == "gemini":
        _apply_gemini_input_and_ambiguity_notes(usage, raw, notes)
    elif p == "claude":
        _apply_claude_cache_conventions(usage, raw, notes)

    if (
        usage["total_tokens"] is not None
        and usage["input_tokens"] is None
        and usage["output_tokens"] is None
        and usage["thinking_tokens"] is None
    ):
        notes.append("usage_dimension_ambiguous:input_tokens")

    return usage, notes


def _catalog_entry_key(entry: Any) -> tuple[str, str] | None:
    if not isinstance(entry, dict):
        return None
    p = str(entry.get("provider", "")).strip().lower()
    m = str(entry.get("model", "")).strip().lower()
    if not p or not m:
        return None
    return (p, m)


@dataclass(frozen=True)
class _PricingResolution:
    entry: dict[str, Any] | None
    canonical_model: str | None
    matched_entry_model: str | None
    #: Catalog row key ``(provider, model)`` used for rates; ``None`` when no row matched.
    matched_catalog_key: tuple[str, str] | None = None
    #: True when an alias mapped the raw model to a canonical id with no catalog row for it.
    alias_resolved_without_entry: bool = False


def _alias_tuple(row: Any) -> tuple[str, str, str] | None:
    if not isinstance(row, dict):
        return None
    p = str(row.get("provider", "")).strip().lower()
    a = str(row.get("alias", "")).strip().lower()
    c = str(row.get("canonical_model", "")).strip().lower()
    if not p or not a or not c:
        return None
    return (p, a, c)


def _operator_catalog_entry_keys(parsed: dict[str, Any]) -> frozenset[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    for ent in parsed.get("entries") or []:
        if isinstance(ent, dict):
            k = _catalog_entry_key(ent)
            if k:
                keys.add(k)
    return frozenset(keys)


def _merge_catalog_aliases(base: dict[str, Any], parsed: dict[str, Any]) -> list[dict[str, Any]]:
    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for row in base.get("aliases") or []:
        t = _alias_tuple(row)
        if t:
            by_key[(t[0], t[1])] = {"provider": t[0], "alias": t[1], "canonical_model": t[2]}
    for row in parsed.get("aliases") or []:
        t = _alias_tuple(row)
        if t:
            by_key[(t[0], t[1])] = {"provider": t[0], "alias": t[1], "canonical_model": t[2]}
    return list(by_key.values())


def _find_exact_catalog_entry(
    catalog: dict[str, Any], provider: str, model_lower: str
) -> dict[str, Any] | None:
    entries = catalog.get("entries")
    if not isinstance(entries, list) or not model_lower:
        return None
    for item in entries:
        if not isinstance(item, dict):
            continue
        ip = str(item.get("provider", "")).strip().lower()
        im = str(item.get("model", "")).strip().lower()
        if ip == provider and im == model_lower:
            return item
    return None


def _find_wildcard_catalog_entry(catalog: dict[str, Any], provider: str) -> dict[str, Any] | None:
    entries = catalog.get("entries")
    if not isinstance(entries, list):
        return None
    for item in entries:
        if not isinstance(item, dict):
            continue
        ip = str(item.get("provider", "")).strip().lower()
        im = str(item.get("model", "")).strip().lower()
        if ip == provider and im in ("*", ""):
            return item
    return None


def resolve_pricing_with_canonical(
    catalog: dict[str, Any], provider: str, raw_model: str
) -> _PricingResolution:
    """Resolve pricing row: exact model, alias → canonical, then provider wildcard."""
    p = (provider or "").strip().lower()
    m_raw = (raw_model or "").strip().lower()

    if m_raw:
        hit = _find_exact_catalog_entry(catalog, p, m_raw)
        if hit is not None:
            mm = str(hit.get("model", "")).strip().lower() or m_raw
            mk = _catalog_entry_key(hit)
            return _PricingResolution(
                hit,
                mm,
                str(hit.get("model", "")).strip() or m_raw,
                mk,
                False,
            )

    if m_raw:
        for row in catalog.get("aliases") or []:
            t = _alias_tuple(row)
            if not t or t[0] != p or t[1] != m_raw:
                continue
            canon = t[2]
            hit = _find_exact_catalog_entry(catalog, p, canon)
            if hit is not None:
                mm = str(hit.get("model", "")).strip().lower() or canon
                mk = _catalog_entry_key(hit)
                return _PricingResolution(
                    hit,
                    mm,
                    str(hit.get("model", "")).strip() or canon,
                    mk,
                    False,
                )
            return _PricingResolution(None, canon, None, None, True)

    wc = _find_wildcard_catalog_entry(catalog, p)
    if wc is not None:
        label = m_raw or "*"
        mk = _catalog_entry_key(wc)
        return _PricingResolution(
            wc,
            label,
            str(wc.get("model", "")).strip() or "*",
            mk,
            False,
        )
    return _PricingResolution(None, m_raw or None, None, None, False)


def _pricing_confidence_for_resolution(
    catalog: dict[str, Any], resolution: _PricingResolution
) -> _PricingConfidence:
    """Whether the matched catalog row came from operator JSON vs embedded-only vs no row."""
    if resolution.entry is None:
        return "unknown"
    mk = resolution.matched_catalog_key
    if mk is None:
        return "embedded_placeholder"
    op = catalog.get("__operator_catalog_entry_keys__")
    if not isinstance(op, (frozenset, set)):
        return "embedded_placeholder"
    if mk in op:
        return "operator_approved"
    return "embedded_placeholder"


def _load_pricing_catalog(settings: Any) -> dict[str, Any]:
    """Load pricing catalog: embedded defaults merged with ``settings.llm_pricing_catalog_json`` (user wins on key clash)."""
    base = copy.deepcopy(_EMBEDDED_DEFAULT_LLM_PRICING_CATALOG)
    raw_attr = getattr(settings, "llm_pricing_catalog_json", "")
    raw = raw_attr.strip() if isinstance(raw_attr, str) else ""
    if not raw:
        base["__operator_catalog_entry_keys__"] = frozenset()
        return base
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("llm.pricing_catalog_invalid_json: using embedded defaults only")
        base["__operator_catalog_entry_keys__"] = frozenset()
        return base
    if not isinstance(parsed, dict):
        base["__operator_catalog_entry_keys__"] = frozenset()
        return base

    operator_keys = _operator_catalog_entry_keys(parsed)

    merged: dict[tuple[str, str], dict[str, Any]] = {}
    for ent in base.get("entries") or []:
        k = _catalog_entry_key(ent)
        if k:
            merged[k] = copy.deepcopy(ent)
    for ent in parsed.get("entries") or []:
        k = _catalog_entry_key(ent)
        if k and isinstance(ent, dict):
            merged[k] = copy.deepcopy(ent)

    ver = parsed.get("version")
    ver_s = str(ver).strip() if ver is not None and str(ver).strip() else ""
    cur = parsed.get("currency")
    cur_s = str(cur).strip() if isinstance(cur, str) and cur.strip() else ""

    out: dict[str, Any] = {
        "version": ver_s or str(base.get("version") or ""),
        "currency": cur_s or str(base.get("currency") or "USD"),
        "source": (
            str(parsed["source"]).strip()
            if isinstance(parsed.get("source"), str) and str(parsed["source"]).strip()
            else "settings.llm_pricing_catalog_json+dinamic_embedded_placeholders"
        ),
        "entries": list(merged.values()),
        "aliases": _merge_catalog_aliases(base, parsed),
        "__operator_catalog_entry_keys__": operator_keys,
    }
    return out


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


def _dedupe_keep_order(items: list[str]) -> list[str]:
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


def _derive_billing_usage_and_refine_notes(
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
        has_thinking_price = _as_decimal(entry.get("thinking_cost_per_million")) is not None
        if tb == "output_tokens":
            o = _to_int(billing.get("output_tokens")) or 0
            th = _to_int(billing.get("thinking_tokens")) or 0
            billing["output_tokens"] = o + th
            billing["thinking_tokens"] = 0
            _strip_notes_with_prefix(notes, "usage_dimension_ambiguous:output_tokens")
        elif has_thinking_price:
            _strip_notes_with_prefix(notes, "usage_dimension_ambiguous:output_tokens")

    if provider_norm == "openai":
        out_t = _to_int(billing.get("output_tokens"))
        think_t = _to_int(billing.get("thinking_tokens"))
        if think_t is not None and think_t > 0 and out_t is not None and think_t <= out_t:
            billing["thinking_tokens"] = 0
            notes.append("usage_assumption:openai_reasoning_tokens_subsumed_by_completion")

    return billing


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
