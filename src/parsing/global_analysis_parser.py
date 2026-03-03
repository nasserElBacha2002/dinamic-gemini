"""
Parseo y validación de la respuesta de análisis global (v2.0).

Convierte el dict JSON en lista de Pallet y aplica validaciones mínimas.
"""

import logging
from typing import Any, Dict, List

from src.domain.pallet import Pallet

logger = logging.getLogger(__name__)


class GlobalAnalysisParseError(Exception):
    """Error al parsear o validar la respuesta de análisis global."""
    pass


def parse_global_analysis(data: Dict[str, Any]) -> List[Pallet]:
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
    result: List[Pallet] = []
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
