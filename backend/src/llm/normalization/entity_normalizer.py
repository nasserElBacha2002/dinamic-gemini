"""
Normalize provider-specific global-analysis JSON into the canonical v2.1 entity shape.

**Canonical contract (``EXTRACTION_CONTRACT_VERSION``):** every entity dict exposes the same keys
used by ``parse_entities`` / hybrid reporting, with explicit ``null`` for unknown optional fields.

**Provider policy:**
- **gemini** / **test_llm** (harness): legacy alias promotion — ``quantity`` / ``qty`` /
  ``detected_quantity`` → ``product_label_quantity`` when canonical qty is absent; ``bbox`` →
  ``product_label_bbox`` when product bbox absent. Gemini structured output already matches
  canonical names; this path is for edge cases and offline tests.
- **openai** (and GPT-family keys resolved to ``openai``): **conservative** promotion when the
  canonical quantity is still unset: a **strictly positive** integer from ``quantity`` / ``qty`` /
  ``detected_quantity`` → ``product_label_quantity`` so PALLET rows are not dropped at persistence
  (UNKNOWN SKU + unresolved zero qty). Generic ``bbox`` is **never** mapped to ``product_label_bbox``;
  when both label bboxes are absent, ``bbox`` is copied to optional ``extent_bbox`` only.
- **deepseek**: same conservative rules as **openai** (Chat Completions–compatible JSON shapes).
- **unknown** (unrecognized ``provider`` string): **no** conservative promotion — vendor-specific
  aliases are stripped; canonical fields stay null unless already set.
- **claude**: **no** blind quantity/bbox alias promotion; map ``product_label`` → ``internal_code``
  when ``internal_code`` is unset and the candidate passes :func:`_is_valid_internal_code`; strip
  ``product_label`` and ``position_label`` (never map free-text position copy into ``position_barcode``).
  ``position_label_bbox`` is already canonical and is preserved.

**Provider names:** Use :func:`resolve_provider_family` so mixed keys (``anthropic``, ``gpt-4.1``,
``openai_sdk``) map to a stable family before branching.

**Prompt alignment:** OpenAI hybrid prompts still encourage numeric output; this module is
defensive so unsafe fields are not promoted. Tighten prompts in a follow-up so model output
matches canonical nullability (see ``openai_sdk_adapter`` JSON suffix).

See also: ``validate_global_analysis_structure_v21`` (adapters) → then this normalizer →
``parse_entities``.
"""

from __future__ import annotations

import copy
import logging
import re
from typing import Any, Dict, List

logger = logging.getLogger("llm.normalization")

# Root-level marker for audit / future migrations; extra keys are ignored by ``parse_entities``.
EXTRACTION_CONTRACT_VERSION_KEY = "extraction_contract_version"
EXTRACTION_CONTRACT_VERSION_VALUE = "global_analysis.v2_1_canonical"

# Providers allowed to promote legacy quantity/bbox aliases into canonical fields (family keys).
_ALIAS_PROMOTE_FAMILIES = frozenset({"gemini", "test_llm"})

# Chat-completions-shaped providers: conservative qty + extent_bbox from generic bbox only.
# ``unknown`` is intentionally excluded — unrecognized providers must not inherit OpenAI semantics.
_OPENAI_FAMILY_CONSERVATIVE_ALIASES = frozenset({"openai"})
_DEEPSEEK_FAMILY_CONSERVATIVE_ALIASES = frozenset({"deepseek"})
_CONSERVATIVE_QTY_PROMOTE_FAMILIES = _OPENAI_FAMILY_CONSERVATIVE_ALIASES | _DEEPSEEK_FAMILY_CONSERVATIVE_ALIASES
_EXTENT_BBOX_FROM_GENERIC_BBOX_FAMILIES = _OPENAI_FAMILY_CONSERVATIVE_ALIASES | _DEEPSEEK_FAMILY_CONSERVATIVE_ALIASES

_ALIAS_KEYS: tuple[str, ...] = ("quantity", "qty", "detected_quantity")

# ``product_label`` → ``internal_code`` only when string looks like a SKU / code (not noisy OCR).
_INTERNAL_CODE_MAX_LEN = 48
_INTERNAL_CODE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

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


def resolve_provider_family(provider: str) -> str:
    """Map a raw provider key (settings, job metadata, SDK label) to a stable normalization family.

    Case-insensitive. Uses substring hints so values like ``gpt-4.1``, ``openai_sdk``,
    ``anthropic``, ``claude-3-opus`` classify correctly.

    Returns one of: ``openai``, ``claude``, ``gemini``, ``deepseek``, ``test_llm``, ``unknown``.
    ``test_llm`` is reserved for the offline executor harness (alias promotion like Gemini).
    """
    p = (provider or "").strip().lower()
    if not p:
        return "unknown"
    if p == "test_llm":
        return "test_llm"
    if "deepseek" in p:
        return "deepseek"
    if "anthropic" in p or "claude" in p:
        return "claude"
    if "gemini" in p or p in ("google_genai", "genai"):
        return "gemini"
    if "openai" in p or "gpt" in p:
        return "openai"
    return "unknown"


def _is_valid_internal_code(value: str) -> bool:
    """Minimal sanity check before promoting Claude ``product_label`` to ``internal_code``."""
    if not value or not isinstance(value, str):
        return False
    s = value.strip()
    if len(s) < 1 or len(s) > _INTERNAL_CODE_MAX_LEN:
        return False
    return bool(_INTERNAL_CODE_PATTERN.fullmatch(s))


def _safe_str(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s if s else None


def _apply_claude_vendor_fields(entity: Dict[str, Any], mapped: List[str]) -> None:
    """Map Claude OCR-style keys into canonical fields; drop vendor-only text."""
    if entity.get("internal_code") in (None, "") and entity.get("product_label") is not None:
        mapped_code = _safe_str(entity.get("product_label"))
        if mapped_code is not None and _is_valid_internal_code(mapped_code):
            entity["internal_code"] = mapped_code
            mapped.append("product_label->internal_code")
            logger.debug(
                "llm.normalization.claude mapped product_label to internal_code (len=%d)",
                len(mapped_code),
            )
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


def _strip_alias_and_bbox_residuals(entity: Dict[str, Any]) -> None:
    """Drop quantity/bbox vendor keys after promotion or conservative path (never leak to parser)."""
    for alt in _ALIAS_KEYS:
        entity.pop(alt, None)
    entity.pop("bbox", None)


def _safe_positive_int_qty(val: Any) -> int | None:
    if val is None or isinstance(val, bool):
        return None
    try:
        q = int(str(val).strip()) if isinstance(val, str) else int(val)
    except (TypeError, ValueError):
        return None
    return q if q > 0 else None


def _maybe_promote_conservative_quantity_alias(
    entity: Dict[str, Any],
    provider_family: str,
    mapped: List[str],
) -> None:
    """If canonical qty is unset, map a positive vendor qty alias (OpenAI-style PALLET payloads)."""
    if provider_family not in _CONSERVATIVE_QTY_PROMOTE_FAMILIES:
        return
    if entity.get("product_label_quantity") is not None:
        return
    for alt in _ALIAS_KEYS:
        if alt not in entity:
            continue
        q = _safe_positive_int_qty(entity.get(alt))
        if q is not None:
            entity["product_label_quantity"] = q
            mapped.append(f"{alt}->product_label_quantity(conservative_qty)")
            break


def _maybe_capture_extent_bbox(
    entity: Dict[str, Any],
    provider_family: str,
    mapped: List[str],
) -> None:
    """Preserve vendor ``bbox`` as ``extent_bbox`` when no specialized label bbox exists."""
    if provider_family not in _EXTENT_BBOX_FROM_GENERIC_BBOX_FAMILIES:
        return
    if entity.get("extent_bbox") is not None:
        return
    if entity.get("product_label_bbox") is not None or entity.get("position_label_bbox") is not None:
        return
    raw = entity.get("bbox")
    if not isinstance(raw, list) or len(raw) != 4:
        return
    try:
        extent = [float(x) for x in raw]
    except (TypeError, ValueError):
        return
    entity["extent_bbox"] = extent
    mapped.append("bbox->extent_bbox")


def _ensure_canonical_entity_keys(entity: Dict[str, Any]) -> None:
    for key in _CANONICAL_ENTITY_KEYS:
        if key not in entity:
            if key == "has_boxes":
                entity[key] = False
            else:
                entity[key] = None


def _normalize_entity(
    entity: Dict[str, Any],
    provider_family: str,
    mapped_accumulator: List[str],
) -> Dict[str, Any]:
    out = dict(entity)

    if provider_family == "claude":
        _apply_claude_vendor_fields(out, mapped_accumulator)

    if provider_family in _ALIAS_PROMOTE_FAMILIES:
        _promote_quantity_bbox_aliases(out, mapped_accumulator)
    _maybe_promote_conservative_quantity_alias(out, provider_family, mapped_accumulator)
    _maybe_capture_extent_bbox(out, provider_family, mapped_accumulator)
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
    - **openai** / **deepseek**: positive qty aliases → ``product_label_quantity`` when canonical qty
      unset; optional ``extent_bbox`` from ``bbox`` when label bboxes unset; then strip residuals.
    - **unknown** provider family: strip aliases only (no promotion). **claude**: strip qty/bbox aliases;
      map ``product_label`` → ``internal_code`` when validated.
    """
    if not isinstance(parsed_json, dict):
        return {}

    out = copy.deepcopy(parsed_json)
    entities = out.get("entities")
    if not isinstance(entities, list):
        return out

    family = resolve_provider_family(provider)
    mapped_all: List[str] = []
    new_entities: List[Any] = []
    for ent in entities:
        if isinstance(ent, dict):
            new_entities.append(_normalize_entity(ent, family, mapped_all))
        else:
            new_entities.append(ent)

    out["entities"] = new_entities
    out["total_entities_detected"] = len(new_entities)
    out[EXTRACTION_CONTRACT_VERSION_KEY] = EXTRACTION_CONTRACT_VERSION_VALUE

    if mapped_all:
        logger.debug(
            "llm.normalization.applied provider_raw=%r family=%s mapped_fields=%r",
            (provider or "").strip(),
            family,
            mapped_all,
        )
    logger.info(
        "v3.normalize_llm_response provider=%r family=%s entities_in=%d entities_out=%d mapped_ops=%d",
        (provider or "").strip(),
        family,
        len(entities),
        len(new_entities),
        len(mapped_all),
    )

    return out
