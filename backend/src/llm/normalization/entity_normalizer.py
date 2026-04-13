"""
Normalize provider-specific global-analysis JSON into the canonical v2.1 entity shape.

**Canonical contract (``EXTRACTION_CONTRACT_VERSION``):** every entity dict exposes the same keys
used by ``parse_entities`` / hybrid reporting, with explicit ``null`` for unknown optional fields.

**Provider policy:**
- **gemini** / **test_llm** (harness): legacy alias promotion — ``quantity`` / ``qty`` /
  ``detected_quantity`` → ``product_label_quantity`` when canonical qty is absent; ``bbox`` →
  ``product_label_bbox`` when product bbox absent. Gemini structured output already matches
  canonical names; this path is for edge cases and offline tests.
- **openai** / **deepseek** / **claude**: **no** blind alias promotion. OpenAI often returns
  ``quantity: 1`` as “one detected unit”, not a read product-label quantity; generic ``bbox`` is
  often scene/pallet extent, not a product-label ROI. Those fields are **stripped** without
  mapping so they cannot contaminate business logic.
- **claude**: map ``product_label`` → ``internal_code`` when ``internal_code`` is unset; strip
  ``product_label`` and ``position_label`` (never map free-text position copy into
  ``position_barcode``). ``position_label_bbox`` is already canonical and is preserved.

**Prompt alignment:** OpenAI hybrid prompts still encourage numeric output; this module is
defensive so unsafe fields are not promoted. Tighten prompts in a follow-up so model output
matches canonical nullability (see ``openai_sdk_adapter`` JSON suffix).

See also: ``validate_global_analysis_structure_v21`` (adapters) → then this normalizer →
``parse_entities``.
"""

from __future__ import annotations

import copy
import logging
from typing import Any, Dict, List

logger = logging.getLogger("llm.normalization")

# Root-level marker for audit / future migrations; extra keys are ignored by ``parse_entities``.
EXTRACTION_CONTRACT_VERSION_KEY = "extraction_contract_version"
EXTRACTION_CONTRACT_VERSION_VALUE = "global_analysis.v2_1_canonical"

# Providers allowed to promote legacy quantity/bbox aliases into canonical fields.
_ALIAS_PROMOTE_PROVIDERS = frozenset({"gemini", "test_llm"})

_ALIAS_KEYS: tuple[str, ...] = ("quantity", "qty", "detected_quantity")

# Every entity entering shared parsing should expose these keys (bool has_boxes uses False if absent).
_CANONICAL_ENTITY_KEYS: tuple[str, ...] = (
    "entity_type",
    "model_entity_id",
    "confidence",
    "has_boxes",
    "source_image_id",
    "position_barcode",
    "internal_code",
    "position_label_bbox",
    "product_label_bbox",
    "product_label_quantity",
)


def _norm_provider(provider: str) -> str:
    return (provider or "").strip().lower() or "unknown"


def _safe_str(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s if s else None


def _apply_claude_vendor_fields(entity: Dict[str, Any], mapped: List[str]) -> None:
    """Map Claude OCR-style keys into canonical fields; drop vendor-only text."""
    if entity.get("internal_code") in (None, "") and entity.get("product_label") is not None:
        mapped_code = _safe_str(entity.get("product_label"))
        if mapped_code is not None:
            entity["internal_code"] = mapped_code
            mapped.append("product_label->internal_code")
    entity.pop("product_label", None)
    entity.pop("position_label", None)


def _promote_quantity_bbox_aliases(entity: Dict[str, Any], mapped: List[str]) -> None:
    if entity.get("product_label_quantity") is None:
        for alt in _ALIAS_KEYS:
            if alt not in entity:
                continue
            val = entity[alt]
            if val is not None:
                entity["product_label_quantity"] = val
                mapped.append(f"{alt}->product_label_quantity")
                break

    if entity.get("product_label_bbox") is None and "bbox" in entity:
        raw_bbox = entity["bbox"]
        if raw_bbox is not None:
            entity["product_label_bbox"] = raw_bbox
            mapped.append("bbox->product_label_bbox")


def _strip_untrusted_aliases(entity: Dict[str, Any]) -> None:
    """Remove vendor aliases without promoting (OpenAI / DeepSeek / Claude)."""
    _strip_alias_and_bbox_residuals(entity)


def _strip_alias_and_bbox_residuals(entity: Dict[str, Any]) -> None:
    """Drop quantity/bbox vendor keys after promotion or conservative strip (never leak to parser)."""
    for alt in _ALIAS_KEYS:
        entity.pop(alt, None)
    entity.pop("bbox", None)


def _ensure_canonical_entity_keys(entity: Dict[str, Any]) -> None:
    for key in _CANONICAL_ENTITY_KEYS:
        if key not in entity:
            if key == "has_boxes":
                entity[key] = False
            else:
                entity[key] = None


def _normalize_entity(
    entity: Dict[str, Any],
    provider_norm: str,
    mapped_accumulator: List[str],
) -> Dict[str, Any]:
    out = dict(entity)

    if provider_norm == "claude":
        _apply_claude_vendor_fields(out, mapped_accumulator)

    if provider_norm in _ALIAS_PROMOTE_PROVIDERS:
        _promote_quantity_bbox_aliases(out, mapped_accumulator)
    else:
        _strip_untrusted_aliases(out)
    _strip_alias_and_bbox_residuals(out)

    _ensure_canonical_entity_keys(out)
    return out


def normalize_llm_response(parsed_json: dict, provider: str) -> dict:
    """
    Return a deep copy of ``parsed_json`` with each entity dict normalized to the canonical v2.1
    extraction shape.

    Sets ``extraction_contract_version`` on the root when an ``entities`` array is normalized.

    Provider-aware rules:
    - **gemini** / **test_llm**: promote quantity/bbox aliases when canonical fields are absent.
    - **openai** / **deepseek** / **claude** (and unknown): strip ``quantity`` / ``qty`` /
      ``detected_quantity`` / ``bbox`` without mapping; Claude additionally maps
      ``product_label`` → ``internal_code``.
    """
    if not isinstance(parsed_json, dict):
        return {}

    out = copy.deepcopy(parsed_json)
    entities = out.get("entities")
    if not isinstance(entities, list):
        return out

    prov = _norm_provider(provider)
    mapped_all: List[str] = []
    new_entities: List[Any] = []
    for ent in entities:
        if isinstance(ent, dict):
            new_entities.append(_normalize_entity(ent, prov, mapped_all))
        else:
            new_entities.append(ent)

    out["entities"] = new_entities
    out["total_entities_detected"] = len(new_entities)
    out[EXTRACTION_CONTRACT_VERSION_KEY] = EXTRACTION_CONTRACT_VERSION_VALUE

    if mapped_all:
        logger.debug(
            "llm.normalization.applied provider=%s mapped_fields=%r",
            prov,
            mapped_all,
        )

    return out
