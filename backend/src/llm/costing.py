"""
Provider-agnostic LLM usage/cost snapshot builder.

The snapshot is persisted with each run for auditability. To avoid overclaiming precision:
- ``total_tokens`` is kept only when reported by the provider payload.
- ambiguous accounting paths are explicitly marked with ``usage_dimension_ambiguous:*`` notes.
"""

from __future__ import annotations

import copy
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Literal

logger = logging.getLogger(__name__)

_MICRO_UNIT = Decimal("1000000")
_MONEY_QUANT = Decimal("0.00000001")

# Merged under operator JSON (``LLM_PRICING_CATALOG_JSON``); user entries override on same
# (provider, model) keys. USD placeholders — tune in deployment catalog or env JSON.
_EMBEDDED_DEFAULT_LLM_PRICING_CATALOG: dict[str, Any] = {
    "version": "dinamic-embedded-pricing-v1",
    "currency": "USD",
    "source": "dinamic_embedded_defaults",
    "entries": [
        {
            "provider": "openai",
            "model": "gpt-5.4",
            "input_cost_per_million": 5,
            "output_cost_per_million": 15,
            "cached_input_cost_per_million": 1.25,
        },
        {
            "provider": "claude",
            "model": "claude-sonnet-4-20250514",
            "input_cost_per_million": 3,
            "output_cost_per_million": 15,
            "cached_input_cost_per_million": 1,
        },
    ],
}


def _utc_iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _to_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return max(0, value)
    if isinstance(value, float):
        if value != value:  # NaN
            return None
        return max(0, int(value))
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        try:
            return max(0, int(raw))
        except ValueError:
            return None
    return None


def _get_first(raw: dict[str, Any], *keys: str) -> int | None:
    for key in keys:
        if key in raw:
            parsed = _to_int(raw.get(key))
            if parsed is not None:
                return parsed
    return None


def _as_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        dec = Decimal(str(value))
    except Exception:
        return None
    return Decimal("0") if dec < 0 else dec


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
        prompt_tokens = _get_first(raw, "prompt_tokens")
        cached = usage["cached_input_tokens"]
        if prompt_tokens is not None and cached is not None:
            usage["input_tokens"] = max(0, prompt_tokens - cached)
            usage["cached_input_tokens"] = cached
        elif prompt_tokens is not None:
            usage["input_tokens"] = prompt_tokens
            notes.append("usage_dimension_ambiguous:cached_input")

    elif p == "gemini":
        prompt_tokens = _get_first(raw, "prompt_token_count")
        cached = _get_first(raw, "cached_content_token_count")
        if prompt_tokens is not None and cached is not None:
            usage["input_tokens"] = max(0, prompt_tokens - cached)
            usage["cached_input_tokens"] = cached
        elif prompt_tokens is not None:
            usage["input_tokens"] = prompt_tokens
            if prompt_tokens > 0:
                notes.append("usage_dimension_ambiguous:cached_input")

        # Gemini responses may expose both candidates and thoughts counts. The API shape in this
        # repo does not guarantee whether thoughts are included in output totals, so we do not
        # derive ``total_tokens`` and we explicitly mark ambiguity.
        cand = _get_first(raw, "candidates_token_count")
        thoughts = _get_first(raw, "thoughts_token_count")
        if cand is not None and thoughts is not None and thoughts > 0:
            notes.append("usage_dimension_ambiguous:output_tokens")

    elif p == "claude":
        # Anthropic Usage fields are present in SDK types, but local code/docs do not prove whether
        # ``input_tokens`` already includes cache-read tokens. Keep conservative accounting:
        # preserve gross input, expose cache-read separately, and mark ambiguity when both appear.
        inp = _get_first(raw, "input_tokens")
        cache_read = _get_first(raw, "cache_read_input_tokens")
        cache_write = _get_first(raw, "cache_creation_input_tokens")
        if cache_write is not None:
            usage["cache_write_tokens"] = cache_write
        if inp is not None:
            usage["input_tokens"] = inp
        if cache_read is not None:
            usage["cached_input_tokens"] = cache_read
            if inp is not None:
                # Distinct from generic ``total-only`` ambiguity: Claude may report both gross
                # ``input_tokens`` and ``cache_read_input_tokens`` without a provable relationship.
                notes.append("usage_dimension_ambiguous:claude_cache_read_vs_gross_input")

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


def _load_pricing_catalog(settings: Any) -> dict[str, Any]:
    """Load pricing catalog: embedded defaults merged with ``settings.llm_pricing_catalog_json`` (user wins on key clash)."""
    base = copy.deepcopy(_EMBEDDED_DEFAULT_LLM_PRICING_CATALOG)
    raw_attr = getattr(settings, "llm_pricing_catalog_json", "")
    raw = raw_attr.strip() if isinstance(raw_attr, str) else ""
    if not raw:
        return base
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("llm.pricing_catalog_invalid_json: using embedded defaults only")
        return base
    if not isinstance(parsed, dict):
        return base

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
            else "settings.llm_pricing_catalog_json+dinamic_embedded_defaults"
        ),
        "entries": list(merged.values()),
    }
    return out


def _resolve_pricing_entry(
    catalog: dict[str, Any], provider: str, model: str
) -> dict[str, Any] | None:
    entries = catalog.get("entries")
    if not isinstance(entries, list):
        return None
    p = (provider or "").strip().lower()
    m = (model or "").strip().lower()
    wildcard: dict[str, Any] | None = None
    for item in entries:
        if not isinstance(item, dict):
            continue
        ip = (
            str(item.get("provider", "")).strip().lower(),
            str(item.get("model", "")).strip().lower(),
        )
        if ip[0] != p:
            continue
        if ip[1] == m:
            return item
        if ip[1] in ("*", ""):
            wildcard = item
    return wildcard


def _compute_per_million(tokens: int, per_million: Decimal) -> Decimal:
    return (Decimal(tokens) * per_million / _MICRO_UNIT).quantize(
        _MONEY_QUANT, rounding=ROUND_HALF_UP
    )


def _compute_unit(units: int, unit_cost: Decimal) -> Decimal:
    return (Decimal(units) * unit_cost).quantize(_MONEY_QUANT, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class BillableDimension:
    usage_key: str
    pricing_key: str | None
    subtotal_key: str | None
    mode: Literal["per_million", "unit", "unpriced"]


_BILLABLE_DIMENSIONS: tuple[BillableDimension, ...] = (
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
    BillableDimension("cache_write_tokens", None, None, "unpriced"),
    BillableDimension("image_input_tokens", None, None, "unpriced"),
)


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


def _usage_int(usage: dict[str, Any], key: str) -> int | None:
    value = usage.get(key)
    return _to_int(value) if value is not None else None


def _has_usage_metadata(usage: dict[str, Any]) -> bool:
    return any(usage.get(key) is not None for key in _USAGE_METADATA_KEYS)


def _format_money_optional(value: Decimal | None) -> str | None:
    """Serialize money-like Decimals as fixed-point strings (avoids ``0E-8`` style output)."""
    if value is None:
        return None
    q = value.quantize(_MONEY_QUANT, rounding=ROUND_HALF_UP)
    return format(q, "f")


def _dedupe_keep_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


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
    - ``unavailable``: no usage metadata from the provider (empty/omitted usage).
    - ``estimated``: usage metadata is present but cost is not fully authoritative: ambiguity notes,
      partial/missing pricing for positive billable usage, or an all-zero usage report that we do not
      treat as evidence of a priced billable call (still not ``exact``).
    - ``exact``: unambiguous accounting and full pricing coverage for all positive billable usage
      dimensions; a stable total can be computed without ambiguity notes.
    """
    provider_norm = (provider or "").strip().lower() or "unknown"
    model_norm = (model or "").strip() or None
    usage, convention_notes = normalize_usage(provider_norm, raw_usage)

    catalog = _load_pricing_catalog(settings)
    entry = _resolve_pricing_entry(catalog, provider_norm, model_norm or "")
    entries_list = catalog.get("entries")
    n_catalog_entries = len(entries_list) if isinstance(entries_list, list) else 0
    if not isinstance(entry, dict):
        logger.info(
            "llm.pricing_entry_missing provider=%s model=%r catalog_entries=%d",
            provider_norm,
            model_norm,
            n_catalog_entries,
        )

    catalog_currency = (
        catalog.get("currency") if isinstance(catalog.get("currency"), str) else None
    ) or "USD"
    pricing_version = (
        (catalog.get("version") if isinstance(catalog.get("version"), str) else None)
        or (getattr(settings, "llm_pricing_catalog_version", "") or "").strip()
        or None
    )
    pricing_source = (
        catalog.get("source") if isinstance(catalog.get("source"), str) else None
    ) or "settings.llm_pricing_catalog_json"
    catalog_entry_captured_at = (
        str(entry.get("captured_at")).strip()
        if isinstance(entry, dict)
        and entry.get("captured_at") is not None
        and str(entry.get("captured_at")).strip()
        else None
    )

    pricing_snapshot: dict[str, Any] = {
        "pricing_source": pricing_source,
        "pricing_version": pricing_version,
        "captured_at": _utc_iso_now(),
        "pricing_catalog_entry_captured_at": catalog_entry_captured_at,
        "billing_currency": catalog_currency,
        "input_cost_per_million": None,
        "output_cost_per_million": None,
        "cached_input_cost_per_million": None,
        "thinking_cost_per_million": None,
        "tool_request_unit_cost": None,
        "image_input_unit_cost": None,
        "audio_input_cost_per_million": None,
        "video_input_cost_per_million": None,
        "thinking_cost_rule": None,
    }

    if isinstance(entry, dict):
        currency_raw = entry.get("currency")
        if isinstance(currency_raw, str) and currency_raw.strip():
            pricing_snapshot["billing_currency"] = currency_raw.strip()
        for key in (
            "input_cost_per_million",
            "output_cost_per_million",
            "cached_input_cost_per_million",
            "thinking_cost_per_million",
            "tool_request_unit_cost",
            "image_input_unit_cost",
            "audio_input_cost_per_million",
            "video_input_cost_per_million",
        ):
            pricing_snapshot[key] = _as_decimal(entry.get(key))
        if entry.get("thinking_cost_rule") is not None:
            pricing_snapshot["thinking_cost_rule"] = (
                str(entry.get("thinking_cost_rule")).strip() or None
            )

    subtotals: dict[str, Decimal | None] = {
        "subtotal_input": None,
        "subtotal_output": None,
        "subtotal_cached": None,
        "subtotal_thinking": None,
        "subtotal_tools": None,
        "subtotal_image": None,
        "subtotal_audio": None,
        "subtotal_video": None,
    }

    has_usage_metadata = _has_usage_metadata(usage)
    has_billable_usage_signal = False
    notes: list[str] = list(convention_notes)
    unpriced_dimension_present = False

    for dim in _BILLABLE_DIMENSIONS:
        amount = _usage_int(usage, dim.usage_key)
        if amount is None:
            continue
        if amount > 0:
            has_billable_usage_signal = True

        if dim.mode == "unpriced":
            unpriced_dimension_present = True
            notes.append(f"billable_dimension_not_priced:{dim.usage_key}")
            continue

        if dim.pricing_key is None or dim.subtotal_key is None:
            continue
        price = pricing_snapshot.get(dim.pricing_key)
        if price is None:
            notes.append(f"billable_dimension_not_priced:{dim.usage_key}")
            continue

        assert isinstance(price, Decimal)
        if dim.mode == "per_million":
            subtotals[dim.subtotal_key] = _compute_per_million(amount, price)
        elif dim.mode == "unit":
            subtotals[dim.subtotal_key] = _compute_unit(amount, price)

    subtotal_values = [v for v in subtotals.values() if v is not None]
    total_cost: Decimal | None = None
    if subtotal_values:
        total_cost = sum(subtotal_values, Decimal("0")).quantize(
            _MONEY_QUANT, rounding=ROUND_HALF_UP
        )

    if not has_usage_metadata:
        notes.append("provider_usage_missing")
    if not isinstance(entry, dict):
        notes.append("pricing_entry_missing")
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
    has_pricing = isinstance(entry, dict)
    pricing_available = has_pricing
    ambiguous = any(note.startswith("usage_dimension_ambiguous:") for note in notes)
    missing_pricing_dimensions = any(
        note.startswith("billable_dimension_not_priced:") for note in notes
    )

    if not has_usage_metadata:
        capture_status = "unavailable"
    elif (
        has_pricing and not ambiguous and not missing_pricing_dimensions and total_cost is not None
    ):
        capture_status = "exact"
    else:
        capture_status = "estimated"

    total_cost_unavailable_reason: str | None = None
    if total_cost is None:
        if "provider_usage_missing" in notes:
            total_cost_unavailable_reason = "provider_usage_missing"
        elif "pricing_entry_missing" in notes:
            total_cost_unavailable_reason = "pricing_entry_missing"
        elif any(n.startswith("billable_dimension_not_priced:") for n in notes):
            total_cost_unavailable_reason = "billable_dimension_not_priced"
        elif "pricing_present_but_no_billable_dimensions" in notes:
            total_cost_unavailable_reason = "pricing_present_but_no_billable_dimensions"
        elif ambiguous:
            total_cost_unavailable_reason = "usage_dimension_ambiguous"
        elif has_usage_metadata:
            total_cost_unavailable_reason = "cost_not_computed"

    return {
        "provider": provider_norm,
        "model": model_norm,
        "pricing_available": pricing_available,
        "billing_currency": pricing_snapshot["billing_currency"],
        "usage": usage,
        "pricing_snapshot": {
            **pricing_snapshot,
            "input_cost_per_million": _format_money_optional(
                pricing_snapshot["input_cost_per_million"]
            ),
            "output_cost_per_million": _format_money_optional(
                pricing_snapshot["output_cost_per_million"]
            ),
            "cached_input_cost_per_million": _format_money_optional(
                pricing_snapshot["cached_input_cost_per_million"]
            ),
            "thinking_cost_per_million": _format_money_optional(
                pricing_snapshot["thinking_cost_per_million"]
            ),
            "tool_request_unit_cost": _format_money_optional(
                pricing_snapshot["tool_request_unit_cost"]
            ),
            "image_input_unit_cost": _format_money_optional(
                pricing_snapshot["image_input_unit_cost"]
            ),
            "audio_input_cost_per_million": _format_money_optional(
                pricing_snapshot["audio_input_cost_per_million"]
            ),
            "video_input_cost_per_million": _format_money_optional(
                pricing_snapshot["video_input_cost_per_million"]
            ),
        },
        "computed_cost": {
            "subtotal_input": _format_money_optional(subtotals["subtotal_input"]),
            "subtotal_output": _format_money_optional(subtotals["subtotal_output"]),
            "subtotal_cached": _format_money_optional(subtotals["subtotal_cached"]),
            "subtotal_thinking": _format_money_optional(subtotals["subtotal_thinking"]),
            "subtotal_tools": _format_money_optional(subtotals["subtotal_tools"]),
            "subtotal_image": _format_money_optional(subtotals["subtotal_image"]),
            "subtotal_audio": _format_money_optional(subtotals["subtotal_audio"]),
            "subtotal_video": _format_money_optional(subtotals["subtotal_video"]),
            "total_cost": _format_money_optional(total_cost),
            "currency": pricing_snapshot["billing_currency"],
            "total_cost_unavailable_reason": total_cost_unavailable_reason,
        },
        "capture_status": capture_status,
        "capture_notes": notes,
    }
