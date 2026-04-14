"""
Provider-agnostic LLM usage/cost snapshot builder.

Captures normalized usage fields from provider-specific raw usage payloads, applies
pricing configuration snapshot from settings, and computes stable cost subtotals.
"""

from __future__ import annotations

import json
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, Optional


_MICRO_UNIT = Decimal("1000000")
_MONEY_QUANT = Decimal("0.00000001")


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


def normalize_usage(provider: str, raw_usage: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Normalize known token/usage fields into a provider-agnostic structure.
    Unknown fields are kept in raw_provider_usage_json for audit.
    """
    raw = raw_usage or {}
    usage: Dict[str, Any] = {
        "input_tokens": _get_first(raw, "input_tokens", "prompt_tokens", "input_token_count", "prompt_token_count"),
        "output_tokens": _get_first(
            raw, "output_tokens", "completion_tokens", "candidates_token_count", "output_token_count"
        ),
        "total_tokens": _get_first(raw, "total_tokens", "total_token_count"),
        "cached_input_tokens": _get_first(
            raw,
            "cached_input_tokens",
            "cached_tokens",
            "cached_content_token_count",
            "cache_read_input_tokens",
        ),
        "cache_write_tokens": _get_first(raw, "cache_write_tokens"),
        "thinking_tokens": _get_first(raw, "thinking_tokens", "thoughts_token_count", "reasoning_tokens"),
        "tool_requests": _get_first(raw, "tool_requests"),
        "image_input_count": _get_first(raw, "image_input_count", "image_count"),
        "image_input_tokens": _get_first(raw, "image_input_tokens"),
        "audio_input_tokens": _get_first(raw, "audio_input_tokens"),
        "video_input_tokens": _get_first(raw, "video_input_tokens"),
        "raw_provider_usage_json": raw,
    }

    # Provider-specific salvage for nested structures without hard coupling.
    input_details = raw.get("input_tokens_details")
    if usage["cached_input_tokens"] is None and isinstance(input_details, dict):
        usage["cached_input_tokens"] = _to_int(input_details.get("cached_tokens"))
    output_details = raw.get("output_tokens_details")
    if usage["thinking_tokens"] is None and isinstance(output_details, dict):
        usage["thinking_tokens"] = _to_int(output_details.get("reasoning_tokens"))
    if usage["tool_requests"] is None and isinstance(raw.get("tool_calls"), list):
        usage["tool_requests"] = len(raw["tool_calls"])

    if usage["total_tokens"] is None:
        inp = usage["input_tokens"] or 0
        out = usage["output_tokens"] or 0
        if inp or out:
            usage["total_tokens"] = inp + out

    return usage


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


def build_llm_cost_snapshot(
    *,
    provider: str,
    model: Optional[str],
    raw_usage: Optional[Dict[str, Any]],
    settings: Any,
) -> Dict[str, Any]:
    """
    Build the auditable usage + pricing + computed-cost snapshot for one LLM call.
    """
    provider_norm = (provider or "").strip().lower() or "unknown"
    model_norm = (model or "").strip() or None
    usage = normalize_usage(provider_norm, raw_usage)
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

    pricing_snapshot: Dict[str, Any] = {
        "pricing_source": pricing_source,
        "pricing_version": pricing_version,
        "captured_at": None,
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
        pricing_snapshot["captured_at"] = (
            str(entry.get("captured_at")).strip() if entry.get("captured_at") is not None else None
        )
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
    if usage["tool_requests"] is not None and tool_unit is not None:
        subtotal_tools = (Decimal(usage["tool_requests"]) * tool_unit).quantize(_MONEY_QUANT, rounding=ROUND_HALF_UP)
    subtotal_image: Optional[Decimal] = None
    image_unit = pricing_snapshot["image_input_unit_cost"]
    if usage["image_input_count"] is not None and image_unit is not None:
        subtotal_image = (Decimal(usage["image_input_count"]) * image_unit).quantize(
            _MONEY_QUANT, rounding=ROUND_HALF_UP
        )
    subtotal_audio = _compute_subtotal(usage["audio_input_tokens"], pricing_snapshot["audio_input_cost_per_million"])
    subtotal_video = _compute_subtotal(usage["video_input_tokens"], pricing_snapshot["video_input_cost_per_million"])

    parts = [subtotal_input, subtotal_output, subtotal_cached, subtotal_thinking, subtotal_tools, subtotal_image, subtotal_audio, subtotal_video]
    total_cost = None
    if any(part is not None for part in parts):
        total_cost = sum((part for part in parts if part is not None), Decimal("0")).quantize(
            _MONEY_QUANT, rounding=ROUND_HALF_UP
        )

    has_usage = any(
        usage[key] is not None
        for key in (
            "input_tokens",
            "output_tokens",
            "total_tokens",
            "cached_input_tokens",
            "cache_write_tokens",
            "thinking_tokens",
            "tool_requests",
        )
    )
    has_pricing = isinstance(entry, dict)
    if has_usage and has_pricing:
        capture_status = "exact" if total_cost is not None else "estimated"
    elif has_usage:
        capture_status = "estimated"
    else:
        capture_status = "unavailable"

    notes: list[str] = []
    if not has_usage:
        notes.append("provider_usage_missing")
    if not has_pricing:
        notes.append("pricing_entry_missing")
    if has_pricing and total_cost is None:
        notes.append("pricing_present_but_no_billable_dimensions")

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
