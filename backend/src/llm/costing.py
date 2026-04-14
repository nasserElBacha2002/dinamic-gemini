"""
Provider-agnostic LLM usage/cost snapshot builder.

Captures normalized usage fields from provider-specific raw usage payloads, applies
pricing configuration snapshot from settings, and computes stable cost subtotals.

Token accounting convention (billing / avoid double-counting)
-------------------------------------------------------------
After normalization, fields mean:

- ``input_tokens``: **non-cached** input tokens billed at the standard input rate.
- ``cached_input_tokens``: tokens billed at the cached-input / cache-read rate (prompt cache hits,
  OpenAI prompt cache, Claude cache read, etc.).
- ``output_tokens``: completion/output tokens billed at the output rate (excluding thinking
  tokens when those are reported separately — see ``thinking_tokens``).
- ``cache_write_tokens``: tokens written to provider-side caches (e.g. Claude cache creation),
  when the API exposes them. There is currently **no** dedicated price field in the catalog
  snapshot for this dimension; presence triggers ``estimated`` status if priced totals cannot
  cover it.
- ``thinking_tokens``: reasoning/thinking tokens when the provider reports them separately from
  output. If a provider cannot prove whether thinking is included in output counts, we add
  ``usage_dimension_ambiguous:<dimension>`` and downgrade to ``estimated``.

Providers differ; when the wire format does not allow a safe split, we record ambiguity notes
and **never** return ``capture_status="exact"``.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Tuple

_MICRO_UNIT = Decimal("1000000")
_MONEY_QUANT = Decimal("0.00000001")


def _utc_iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _to_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else 0
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


def _get_first(raw: Dict[str, Any], *keys: str) -> Optional[int]:
    for key in keys:
        if key in raw:
            parsed = _to_int(raw.get(key))
            if parsed is not None:
                return parsed
    return None


def _as_decimal(value: Any) -> Optional[Decimal]:
    if value is None:
        return None
    try:
        dec = Decimal(str(value))
    except Exception:
        return None
    if dec < 0:
        return Decimal("0")
    return dec


def normalize_usage(provider: str, raw_usage: Optional[Dict[str, Any]]) -> Tuple[Dict[str, Any], List[str]]:
    """
    Normalize known token/usage fields into a provider-agnostic structure.

    Returns ``(usage, convention_notes)``. ``convention_notes`` are machine codes such as
    ``usage_dimension_ambiguous:cached_input`` — they feed ``capture_status`` and UI mapping.

    Original provider keys are preserved under ``raw_provider_usage_json`` for audit.
    """
    notes: List[str] = []
    raw = dict(raw_usage or {})
    p = (provider or "").strip().lower() or "unknown"

    usage: Dict[str, Any] = {
        "input_tokens": _get_first(
            raw,
            "input_tokens",
            "prompt_tokens",
            "input_token_count",
            "prompt_token_count",
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
        "cache_write_tokens": _get_first(
            raw,
            "cache_write_tokens",
            "cache_creation_input_tokens",
        ),
        "thinking_tokens": _get_first(
            raw,
            "thinking_tokens",
            "thoughts_token_count",
            "reasoning_tokens",
        ),
        "tool_requests": _get_first(raw, "tool_requests"),
        "image_input_count": _get_first(raw, "image_input_count", "image_count"),
        "image_input_tokens": _get_first(raw, "image_input_tokens"),
        "audio_input_tokens": _get_first(raw, "audio_input_tokens"),
        "video_input_tokens": _get_first(raw, "video_input_tokens"),
        "raw_provider_usage_json": raw,
    }

    # OpenAI nested details (prompt_tokens_details / completion_tokens_details)
    input_details = raw.get("input_tokens_details") or raw.get("prompt_tokens_details")
    if isinstance(input_details, dict):
        if usage["cached_input_tokens"] is None:
            usage["cached_input_tokens"] = _to_int(input_details.get("cached_tokens"))
    output_details = raw.get("output_tokens_details") or raw.get("completion_tokens_details")
    if isinstance(output_details, dict):
        if usage["thinking_tokens"] is None:
            usage["thinking_tokens"] = _to_int(output_details.get("reasoning_tokens"))
    if usage["tool_requests"] is None and isinstance(raw.get("tool_calls"), list):
        usage["tool_requests"] = len(raw["tool_calls"])

    # --- Provider-specific conventions (non-cached vs cached input) ---
    if p == "openai":
        pt = _get_first(raw, "prompt_tokens")
        cached = usage["cached_input_tokens"]
        if pt is not None and cached is not None:
            usage["input_tokens"] = max(0, pt - cached)
            usage["cached_input_tokens"] = cached
        elif pt is not None:
            usage["input_tokens"] = pt
            if cached is None:
                notes.append("usage_dimension_ambiguous:cached_input")
    elif p == "gemini":
        pt = _get_first(raw, "prompt_token_count")
        cc = _get_first(raw, "cached_content_token_count")
        if pt is not None and cc is not None:
            usage["input_tokens"] = max(0, pt - cc)
            usage["cached_input_tokens"] = cc
        elif pt is not None:
            usage["input_tokens"] = pt
            if cc is None and pt > 0:
                notes.append("usage_dimension_ambiguous:cached_input")
    elif p == "claude":
        inp = _get_first(raw, "input_tokens")
        cread = _get_first(raw, "cache_read_input_tokens")
        cwrite = _get_first(raw, "cache_creation_input_tokens")
        if cwrite is not None:
            usage["cache_write_tokens"] = cwrite
        if inp is not None and cread is not None:
            if cread > inp:
                notes.append("usage_dimension_ambiguous:input_tokens")
                usage["input_tokens"] = inp
                usage["cached_input_tokens"] = cread
            else:
                usage["input_tokens"] = max(0, inp - cread)
                usage["cached_input_tokens"] = cread
        elif inp is not None:
            usage["input_tokens"] = inp
            if cread is not None:
                usage["cached_input_tokens"] = cread

    # Derive total_tokens when missing. If both input and output are already known and there is no
    # separate thinking stream, the sum is unambiguous for totals display (no note).
    if usage["total_tokens"] is None:
        inp = usage["input_tokens"] or 0
        out = usage["output_tokens"] or 0
        think = usage["thinking_tokens"] or 0
        if inp or out or think:
            usage["total_tokens"] = inp + out + think
            if (
                think
                or usage["input_tokens"] is None
                or usage["output_tokens"] is None
            ):
                notes.append("usage_dimension_ambiguous:total_tokens")

    if (
        usage["total_tokens"] is not None
        and usage["input_tokens"] is None
        and usage["output_tokens"] is None
        and usage["thinking_tokens"] is None
    ):
        notes.append("usage_dimension_ambiguous:input_tokens")

    # Gemini / multi-token: if both output and thinking present, total may double-count
    if p == "gemini":
        cand = _get_first(raw, "candidates_token_count")
        thoughts = _get_first(raw, "thoughts_token_count")
        if cand is not None and thoughts is not None and thoughts > 0:
            notes.append("usage_dimension_ambiguous:output_tokens")

    return usage, notes


def _load_pricing_catalog(settings: Any) -> Dict[str, Any]:
    raw = (getattr(settings, "llm_pricing_catalog_json", "") or "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _resolve_pricing_entry(catalog: Dict[str, Any], provider: str, model: str) -> Optional[Dict[str, Any]]:
    entries = catalog.get("entries")
    if not isinstance(entries, list):
        return None
    p = (provider or "").strip().lower()
    m = (model or "").strip()
    wildcard: Optional[Dict[str, Any]] = None
    for item in entries:
        if not isinstance(item, dict):
            continue
        ip = (str(item.get("provider", "")).strip().lower(), str(item.get("model", "")).strip())
        if ip[0] != p:
            continue
        if ip[1] == m:
            return item
        if ip[1] in ("*", ""):
            wildcard = item
    return wildcard


def _compute_subtotal(tokens: Optional[int], per_million: Optional[Decimal]) -> Optional[Decimal]:
    if tokens is None or per_million is None:
        return None
    return (Decimal(tokens) * per_million / _MICRO_UNIT).quantize(_MONEY_QUANT, rounding=ROUND_HALF_UP)


# (usage_key, pricing_snapshot_key) — dimensions we can price via catalog fields.
_PRICED_DIMENSIONS: Tuple[Tuple[str, str], ...] = (
    ("input_tokens", "input_cost_per_million"),
    ("output_tokens", "output_cost_per_million"),
    ("cached_input_tokens", "cached_input_cost_per_million"),
    ("thinking_tokens", "thinking_cost_per_million"),
    ("audio_input_tokens", "audio_input_cost_per_million"),
    ("video_input_tokens", "video_input_cost_per_million"),
)

# Usage keys that count as billable if > 0 but have no catalog price field in this design.
_UNPRICED_USAGE_KEYS: Tuple[str, ...] = ("cache_write_tokens",)


def _usage_int(usage: Dict[str, Any], key: str) -> Optional[int]:
    v = usage.get(key)
    return _to_int(v) if v is not None else None


def build_llm_cost_snapshot(
    *,
    provider: str,
    model: Optional[str],
    raw_usage: Optional[Dict[str, Any]],
    settings: Any,
) -> Dict[str, Any]:
    """
    Build the auditable usage + pricing + computed-cost snapshot for one LLM call.

    ``capture_status``:
    - ``exact``: all strictly positive billable usage dimensions that appear in normalized usage
      have a matching non-null catalog price, subtotals are computed for each, and there are no
      ambiguity or coverage notes.
    - ``estimated``: usage exists but pricing is incomplete, or notes indicate ambiguity/partial
      coverage.
    - ``unavailable``: no meaningful usage to estimate cost.
    """
    provider_norm = (provider or "").strip().lower() or "unknown"
    model_norm = (model or "").strip() or None
    usage, convention_notes = normalize_usage(provider_norm, raw_usage)
    catalog = _load_pricing_catalog(settings)
    entry = _resolve_pricing_entry(catalog, provider_norm, model_norm or "")

    catalog_currency = (catalog.get("currency") if isinstance(catalog.get("currency"), str) else None) or "USD"
    pricing_version = (
        (catalog.get("version") if isinstance(catalog.get("version"), str) else None)
        or (getattr(settings, "llm_pricing_catalog_version", "") or "").strip()
        or None
    )
    pricing_source = (
        (catalog.get("source") if isinstance(catalog.get("source"), str) else None)
        or "settings.llm_pricing_catalog_json"
    )

    catalog_entry_captured_at: Optional[str] = None
    if isinstance(entry, dict) and entry.get("captured_at") is not None:
        catalog_entry_captured_at = str(entry.get("captured_at")).strip() or None

    pricing_snapshot: Dict[str, Any] = {
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
        if isinstance(entry.get("currency"), str) and entry.get("currency").strip():
            pricing_snapshot["billing_currency"] = str(entry["currency"]).strip()
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
            pricing_snapshot["thinking_cost_rule"] = str(entry.get("thinking_cost_rule")).strip() or None

    subtotal_input = _compute_subtotal(usage["input_tokens"], pricing_snapshot["input_cost_per_million"])
    subtotal_output = _compute_subtotal(usage["output_tokens"], pricing_snapshot["output_cost_per_million"])
    subtotal_cached = _compute_subtotal(
        usage["cached_input_tokens"],
        pricing_snapshot["cached_input_cost_per_million"],
    )
    subtotal_thinking = _compute_subtotal(
        usage["thinking_tokens"],
        pricing_snapshot["thinking_cost_per_million"],
    )
    subtotal_tools: Optional[Decimal] = None
    tool_unit = pricing_snapshot["tool_request_unit_cost"]
    tr = _usage_int(usage, "tool_requests")
    if tr is not None and tool_unit is not None:
        subtotal_tools = (Decimal(tr) * tool_unit).quantize(_MONEY_QUANT, rounding=ROUND_HALF_UP)
    subtotal_image: Optional[Decimal] = None
    image_unit = pricing_snapshot["image_input_unit_cost"]
    ii = _usage_int(usage, "image_input_count")
    if ii is not None and image_unit is not None:
        subtotal_image = (Decimal(ii) * image_unit).quantize(_MONEY_QUANT, rounding=ROUND_HALF_UP)
    subtotal_audio = _compute_subtotal(usage["audio_input_tokens"], pricing_snapshot["audio_input_cost_per_million"])
    subtotal_video = _compute_subtotal(usage["video_input_tokens"], pricing_snapshot["video_input_cost_per_million"])

    parts = [
        subtotal_input,
        subtotal_output,
        subtotal_cached,
        subtotal_thinking,
        subtotal_tools,
        subtotal_image,
        subtotal_audio,
        subtotal_video,
    ]
    total_cost: Optional[Decimal] = None
    if any(part is not None for part in parts):
        total_cost = sum((part for part in parts if part is not None), Decimal("0")).quantize(
            _MONEY_QUANT, rounding=ROUND_HALF_UP
        )

    has_usage_signal = any(
        _usage_int(usage, k) not in (None, 0)
        for k in (
            "input_tokens",
            "output_tokens",
            "cached_input_tokens",
            "cache_write_tokens",
            "thinking_tokens",
            "tool_requests",
            "image_input_count",
            "image_input_tokens",
            "audio_input_tokens",
            "video_input_tokens",
        )
    ) or (usage.get("total_tokens") is not None and _to_int(usage.get("total_tokens")) not in (None, 0))

    notes: List[str] = list(convention_notes)
    if not has_usage_signal:
        notes.append("provider_usage_missing")
    if not isinstance(entry, dict):
        notes.append("pricing_entry_missing")

    # Billable dimensions: positive usage requires a price (or explicit unpriced handling).
    missing_price_dims: List[str] = []
    if isinstance(entry, dict):
        for ukey, pkey in _PRICED_DIMENSIONS:
            n = _usage_int(usage, ukey)
            if n is not None and n > 0:
                if pricing_snapshot.get(pkey) is None:
                    missing_price_dims.append(ukey)
        trc = _usage_int(usage, "tool_requests")
        if trc is not None and trc > 0 and pricing_snapshot["tool_request_unit_cost"] is None:
            missing_price_dims.append("tool_requests")
        iic = _usage_int(usage, "image_input_count")
        if iic is not None and iic > 0 and pricing_snapshot["image_input_unit_cost"] is None:
            missing_price_dims.append("image_input_count")
        iit = _usage_int(usage, "image_input_tokens")
        if iit is not None and iit > 0:
            notes.append("billable_dimension_not_priced:image_input_tokens")

    for uk in _UNPRICED_USAGE_KEYS:
        n = _usage_int(usage, uk)
        if n is not None and n > 0:
            notes.append(f"billable_dimension_not_priced:{uk}")

    for d in missing_price_dims:
        notes.append(f"billable_dimension_not_priced:{d}")

    if isinstance(entry, dict) and has_usage_signal and total_cost is None and not missing_price_dims:
        # Pricing row exists but no line items matched (e.g. only unsupported dimensions).
        pos_priced = any(
            _usage_int(usage, ukey) not in (None, 0)
            for ukey, pkey in _PRICED_DIMENSIONS
            if pricing_snapshot.get(pkey) is not None
        ) or (
            tr is not None
            and tr > 0
            and pricing_snapshot["tool_request_unit_cost"] is not None
        ) or (
            ii is not None
            and ii > 0
            and pricing_snapshot["image_input_unit_cost"] is not None
        )
        if not pos_priced:
            notes.append("pricing_present_but_no_billable_dimensions")

    # De-duplicate notes (preserve order)
    seen: set[str] = set()
    deduped: List[str] = []
    for n in notes:
        if n not in seen:
            seen.add(n)
            deduped.append(n)
    notes = deduped

    ambiguous = any(n.startswith("usage_dimension_ambiguous:") for n in notes)
    has_pricing = isinstance(entry, dict)
    priced_coverage_ok = has_pricing and not any(
        n.startswith("billable_dimension_not_priced:") for n in notes
    )

    if not has_usage_signal:
        capture_status = "unavailable"
    elif (
        priced_coverage_ok
        and total_cost is not None
        and not ambiguous
        and "pricing_entry_missing" not in notes
        and "provider_usage_missing" not in notes
    ):
        capture_status = "exact"
    elif has_usage_signal:
        capture_status = "estimated"
    else:
        capture_status = "unavailable"

    return {
        "provider": provider_norm,
        "model": model_norm,
        "billing_currency": pricing_snapshot["billing_currency"],
        "usage": usage,
        "pricing_snapshot": {
            **pricing_snapshot,
            "input_cost_per_million": str(pricing_snapshot["input_cost_per_million"])
            if pricing_snapshot["input_cost_per_million"] is not None
            else None,
            "output_cost_per_million": str(pricing_snapshot["output_cost_per_million"])
            if pricing_snapshot["output_cost_per_million"] is not None
            else None,
            "cached_input_cost_per_million": str(pricing_snapshot["cached_input_cost_per_million"])
            if pricing_snapshot["cached_input_cost_per_million"] is not None
            else None,
            "thinking_cost_per_million": str(pricing_snapshot["thinking_cost_per_million"])
            if pricing_snapshot["thinking_cost_per_million"] is not None
            else None,
            "tool_request_unit_cost": str(pricing_snapshot["tool_request_unit_cost"])
            if pricing_snapshot["tool_request_unit_cost"] is not None
            else None,
            "image_input_unit_cost": str(pricing_snapshot["image_input_unit_cost"])
            if pricing_snapshot["image_input_unit_cost"] is not None
            else None,
            "audio_input_cost_per_million": str(pricing_snapshot["audio_input_cost_per_million"])
            if pricing_snapshot["audio_input_cost_per_million"] is not None
            else None,
            "video_input_cost_per_million": str(pricing_snapshot["video_input_cost_per_million"])
            if pricing_snapshot["video_input_cost_per_million"] is not None
            else None,
        },
        "computed_cost": {
            "subtotal_input": str(subtotal_input) if subtotal_input is not None else None,
            "subtotal_output": str(subtotal_output) if subtotal_output is not None else None,
            "subtotal_cached": str(subtotal_cached) if subtotal_cached is not None else None,
            "subtotal_thinking": str(subtotal_thinking) if subtotal_thinking is not None else None,
            "subtotal_tools": str(subtotal_tools) if subtotal_tools is not None else None,
            "subtotal_image": str(subtotal_image) if subtotal_image is not None else None,
            "subtotal_audio": str(subtotal_audio) if subtotal_audio is not None else None,
            "subtotal_video": str(subtotal_video) if subtotal_video is not None else None,
            "total_cost": str(total_cost) if total_cost is not None else None,
            "currency": pricing_snapshot["billing_currency"],
        },
        "capture_status": capture_status,
        "capture_notes": notes,
    }
