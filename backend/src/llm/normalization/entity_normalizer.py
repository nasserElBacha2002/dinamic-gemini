"""
Normalize provider-specific global-analysis JSON into the canonical v2.1 entity shape.

Phase 5 compatibility: OpenAI may use alternate field names; Gemini paths should be unchanged.
"""

from __future__ import annotations

import copy
import logging
from typing import Any, Dict, List

logger = logging.getLogger("llm.normalization")

_REQUIRED_ENTITY_FIELDS: tuple[str, ...] = (
    "position_barcode",
    "internal_code",
    "position_label_bbox",
    "product_label_bbox",
    "product_label_quantity",
)

_ALIAS_KEYS: tuple[str, ...] = ("quantity", "qty", "detected_quantity")


def _normalize_entity(entity: Dict[str, Any], mapped_accumulator: List[str]) -> Dict[str, Any]:
    out = dict(entity)

    for key in _REQUIRED_ENTITY_FIELDS:
        if key not in out:
            out[key] = None

    if out.get("product_label_quantity") is None:
        for alt in _ALIAS_KEYS:
            if alt not in out:
                continue
            val = out[alt]
            if val is not None:
                out["product_label_quantity"] = val
                mapped_accumulator.append(f"{alt}->product_label_quantity")
                break

    # Bbox: OpenAI-style ``bbox`` → ``product_label_bbox`` (PALLET and others: never map to
    # position_label_bbox). Do not override an existing product_label_bbox.
    if out.get("product_label_bbox") is None and "bbox" in out:
        raw_bbox = out["bbox"]
        if raw_bbox is not None:
            out["product_label_bbox"] = raw_bbox
            mapped_accumulator.append("bbox->product_label_bbox")

    for alt in _ALIAS_KEYS:
        out.pop(alt, None)
    out.pop("bbox", None)

    return out


def normalize_llm_response(parsed_json: dict, provider: str) -> dict:
    """
    Return a deep copy of ``parsed_json`` with each entity dict normalized.

    - Maps ``quantity`` / ``qty`` / ``detected_quantity`` into ``product_label_quantity`` when
      the canonical field is missing or null.
    - Maps ``bbox`` into ``product_label_bbox`` when that field is missing or null (not to
      ``position_label_bbox``).
    - Ensures canonical optional fields exist (null if absent).
    - Drops alias keys and ``bbox`` after mapping.
    """
    if not isinstance(parsed_json, dict):
        return {}

    out = copy.deepcopy(parsed_json)
    entities = out.get("entities")
    if not isinstance(entities, list):
        return out

    mapped_all: List[str] = []
    new_entities: List[Any] = []
    for ent in entities:
        if isinstance(ent, dict):
            new_entities.append(_normalize_entity(ent, mapped_all))
        else:
            new_entities.append(ent)

    out["entities"] = new_entities

    if mapped_all:
        logger.debug(
            "llm.normalization.applied provider=%s mapped_fields=%r",
            (provider or "").strip().lower() or "unknown",
            mapped_all,
        )

    return out
