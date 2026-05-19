"""Pricing catalog load, merge, and model resolution."""

from __future__ import annotations

import copy
import json
import logging
from dataclasses import dataclass
from typing import Any, Literal

from src.llm.costing_helpers.catalog_defaults import EMBEDDED_DEFAULT_LLM_PRICING_CATALOG

logger = logging.getLogger(__name__)

PricingConfidence = Literal["operator_approved", "embedded_placeholder", "unknown"]


def _catalog_entry_key(entry: Any) -> tuple[str, str] | None:
    if not isinstance(entry, dict):
        return None
    p = str(entry.get("provider", "")).strip().lower()
    m = str(entry.get("model", "")).strip().lower()
    if not p or not m:
        return None
    return (p, m)


@dataclass(frozen=True)
class PricingResolution:
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
) -> PricingResolution:
    """Resolve pricing row: exact model, alias → canonical, then provider wildcard."""
    p = (provider or "").strip().lower()
    m_raw = (raw_model or "").strip().lower()

    if m_raw:
        hit = _find_exact_catalog_entry(catalog, p, m_raw)
        if hit is not None:
            mm = str(hit.get("model", "")).strip().lower() or m_raw
            mk = _catalog_entry_key(hit)
            return PricingResolution(
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
                return PricingResolution(
                    hit,
                    mm,
                    str(hit.get("model", "")).strip() or canon,
                    mk,
                    False,
                )
            return PricingResolution(None, canon, None, None, True)

    wc = _find_wildcard_catalog_entry(catalog, p)
    if wc is not None:
        label = m_raw or "*"
        mk = _catalog_entry_key(wc)
        return PricingResolution(
            wc,
            label,
            str(wc.get("model", "")).strip() or "*",
            mk,
            False,
        )
    return PricingResolution(None, m_raw or None, None, None, False)


def _pricing_confidence_for_resolution(
    catalog: dict[str, Any], resolution: PricingResolution
) -> PricingConfidence:
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


def load_pricing_catalog(settings: Any) -> dict[str, Any]:
    """Load pricing catalog: embedded defaults merged with ``settings.llm_pricing_catalog_json`` (user wins on key clash)."""
    base = copy.deepcopy(EMBEDDED_DEFAULT_LLM_PRICING_CATALOG)
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
