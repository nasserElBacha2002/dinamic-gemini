"""
Parseo y validación de la respuesta de análisis global (v2.0 y v2.1).

v2.0: convierte el dict JSON en lista de Pallet.
v2.1: convierte el dict JSON en lista de Entity con entity_uid y original_index.
"""

import logging
from typing import Any, Optional

from src.domain.entity import Entity
from src.domain.manifest_evidence_resolution import raw_evidence_from_entity_dict
from src.domain.pallet import Pallet

logger = logging.getLogger(__name__)


class GlobalAnalysisParseError(Exception):
    """Error al parsear o validar la respuesta de análisis global."""

    pass


def parse_global_analysis(data: dict[str, Any]) -> list[Pallet]:
    """Convierte el dict de respuesta global en lista de Pallet con validaciones.

    Validaciones (Stage 2 mínimas):
    - total_pallets_detected == len(pallets)
    - pallet_id únicos
    - confidence en [0, 1]
    - keys requeridas presentes
    - Si has_label true y quantity es null, se loguea warning (strict en Stage 4/6).

    Args:
        data: Dict con "total_pallets_detected" y "pallets".

    Returns:
        Lista de Pallet.

    Raises:
        GlobalAnalysisParseError: Si validación falla o estructura inválida.
    """
    if not isinstance(data, dict):
        raise GlobalAnalysisParseError("Respuesta debe ser un objeto JSON")
    total = data.get("total_pallets_detected")
    pallets_raw = data.get("pallets")
    if total is None:
        raise GlobalAnalysisParseError("Falta 'total_pallets_detected'")
    if pallets_raw is None:
        raise GlobalAnalysisParseError("Falta 'pallets'")
    if not isinstance(pallets_raw, list):
        raise GlobalAnalysisParseError("'pallets' debe ser un array")
    if total != len(pallets_raw):
        raise GlobalAnalysisParseError(
            f"total_pallets_detected ({total}) != len(pallets) ({len(pallets_raw)})"
        )
    seen_ids = set()
    result: list[Pallet] = []
    for i, p in enumerate(pallets_raw):
        if not isinstance(p, dict):
            raise GlobalAnalysisParseError(f"pallets[{i}] debe ser un objeto")
        pallet_id = p.get("pallet_id")
        if pallet_id is None:
            raise GlobalAnalysisParseError(f"pallets[{i}] sin 'pallet_id'")
        if pallet_id in seen_ids:
            raise GlobalAnalysisParseError(f"pallet_id duplicado: {pallet_id!r}")
        seen_ids.add(pallet_id)
        confidence = p.get("confidence")
        if confidence is None:
            raise GlobalAnalysisParseError(f"pallets[{i}] sin 'confidence'")
        try:
            c = float(confidence)
        except (TypeError, ValueError):
            raise GlobalAnalysisParseError(f"pallets[{i}].confidence no es número: {confidence!r}")
        if not (0 <= c <= 1):
            raise GlobalAnalysisParseError(f"pallets[{i}].confidence fuera de [0,1]: {c}")
        has_label = p.get("has_label", False)
        quantity = p.get("quantity")
        if has_label and quantity is None:
            logger.warning("Pallet %s: has_label=true pero quantity=null", pallet_id)
        internal_code = p.get("internal_code")
        if internal_code is not None and not isinstance(internal_code, str):
            internal_code = str(internal_code)
        quantity_int = None
        if quantity is not None:
            try:
                quantity_int = int(quantity)
            except (TypeError, ValueError):
                quantity_int = None
        est_boxes = p.get("estimated_visible_boxes")
        est_boxes_int = None
        if est_boxes is not None:
            try:
                est_boxes_int = int(est_boxes)
            except (TypeError, ValueError):
                est_boxes_int = None
        result.append(
            Pallet(
                pallet_id=str(pallet_id),
                has_label=bool(has_label),
                internal_code=internal_code,
                quantity=quantity_int,
                estimated_visible_boxes=est_boxes_int,
                confidence=c,
                processing_mode=None,
            )
        )
    return result


def _safe_str(v: Any) -> Optional[str]:
    """Return string or None; empty string becomes None."""
    if v is None:
        return None
    s = str(v).strip()
    return s if s else None


def _safe_int(v: Any) -> Optional[int]:
    """Coerce to int or None."""
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _safe_bbox(v: Any) -> Optional[list[float]]:
    """Return [x1,y1,x2,y2] as list of float or None. Preserves float precision (normalized coords)."""
    if v is None:
        return None
    if not isinstance(v, list) or len(v) != 4:
        return None
    try:
        return [float(x) for x in v]
    except (TypeError, ValueError):
        return None


def parse_entities(data: dict[str, Any], job_id: str = "") -> list[Entity]:
    """Convert v2.1 global analysis dict into list of Entity.

    Call after validate_global_analysis_structure_v21. Sets entity_uid from
    job_id + model_entity_id and original_index from list position for
    deterministic ordering.

    source_image_id (Epic 3.1.B): Normalized via _safe_str — leading/trailing
    whitespace stripped, empty string becomes None. Casing is preserved.
    Structural validation (e.g. allowed format) is left to the traceability
    validation layer; parser only captures and normalizes.

    Args:
        data: Dict with total_entities_detected and entities (validated).
        job_id: Job identifier for stable entity_uid (default "").

    Returns:
        List of Entity with entity_uid, original_index, and all parsed fields.
    """
    if not isinstance(data, dict):
        raise GlobalAnalysisParseError("Response must be a JSON object")
    entities_raw = data.get("entities")
    if not isinstance(entities_raw, list):
        raise GlobalAnalysisParseError("'entities' must be an array")

    result: list[Entity] = []
    for i, e in enumerate(entities_raw):
        if not isinstance(e, dict):
            raise GlobalAnalysisParseError(f"entities[{i}] must be an object")

        model_entity_id = e.get("model_entity_id")
        if model_entity_id is None:
            raise GlobalAnalysisParseError(f"entities[{i}] missing 'model_entity_id'")
        entity_uid = f"{job_id}_{model_entity_id}" if job_id else str(model_entity_id)

        entity_type = e.get("entity_type", "PALLET")
        if entity_type not in ("PALLET", "EMPTY_PALLET", "LOOSE_BOXES"):
            raise GlobalAnalysisParseError(f"entities[{i}].entity_type invalid: {entity_type!r}")

        confidence = 0.0
        c = e.get("confidence")
        if c is not None:
            try:
                confidence = float(c)
            except (TypeError, ValueError):
                pass
        confidence = max(0.0, min(1.0, confidence))

        qty = _safe_int(e.get("product_label_quantity"))

        raw = raw_evidence_from_entity_dict(e)

        result.append(
            Entity(
                entity_uid=entity_uid,
                entity_type=entity_type,
                model_entity_id=str(model_entity_id),
                position_barcode=_safe_str(e.get("position_barcode")),
                position_label_bbox=_safe_bbox(e.get("position_label_bbox")),
                internal_code=_safe_str(e.get("internal_code")),
                product_label_quantity=qty,
                product_label_bbox=_safe_bbox(e.get("product_label_bbox")),
                extent_bbox=_safe_bbox(e.get("extent_bbox")),
                has_boxes=bool(e.get("has_boxes", False)),
                confidence=confidence,
                pallet_id=None,
                pallet_id_method=None,
                count_status=None,
                final_quantity=None,
                conflict_flag=False,
                conflict_reason=None,
                entity_quality_score=0.0,
                original_index=i,
                manifest_entry_id=raw.manifest_entry_id,
                raw_source_image_id=raw.legacy_source_image_id,
                source_image_id=None,
                traceability_status=None,
                traceability_warning=None,
            )
        )
    return result
