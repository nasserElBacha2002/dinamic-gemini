"""Map consolidated positions to flat dict rows for CSV export.

Delegates quantity/traceability/summary semantics to ``position_to_summary`` (v3 API parity).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from src.application.utils.natural_sort import natural_sort_key_parts
from src.domain.aisle.entities import Aisle
from src.domain.inventory.entities import Inventory
from src.domain.positions.entities import Position
from src.domain.products.entities import ProductRecord


def _summary_dict(p: Position) -> Dict[str, Any]:
    j = p.detected_summary_json if isinstance(p.detected_summary_json, dict) else {}
    return j


def export_position_code(p: Position) -> str:
    j = _summary_dict(p)
    for k in ("pallet_id", "position_barcode", "entity_uid"):
        v = j.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return p.id


def export_position_sort_key(p: Position) -> tuple:
    """Deterministic ordering within an aisle after consolidation."""
    j = _summary_dict(p)
    internal = j.get("internal_code")
    internal_s = internal.strip() if isinstance(internal, str) else ""
    return (
        natural_sort_key_parts(export_position_code(p)),
        natural_sort_key_parts(internal_s),
        p.created_at,
        p.id,
    )


def position_to_export_row_dict(
    inventory: Inventory,
    aisle: Aisle,
    aisle_sequence: int,
    position: Position,
    primary_product: Optional[ProductRecord],
) -> Dict[str, Any]:
    # Local import avoids circular import: api.dependencies → export use case → this module → api.shared → router.
    from src.api.routes.v3.shared import position_to_summary

    corrected = primary_product.corrected_quantity if primary_product is not None else None
    summary = position_to_summary(
        position,
        corrected_quantity=corrected,
        primary_product=primary_product,
    )
    j = _summary_dict(position)
    internal_code = j.get("internal_code")
    internal_s = internal_code.strip() if isinstance(internal_code, str) else ""
    barcode_v = j.get("position_barcode")
    barcode_s = barcode_v.strip() if isinstance(barcode_v, str) else ""
    label_raw = j.get("review_display_label")
    product_label = (
        (primary_product.description or "").strip()
        if primary_product is not None
        else (label_raw.strip() if isinstance(label_raw, str) else "")
    )
    qty_src = (primary_product.qty_source or "").strip() if primary_product else summary.qtySource
    qty_reason = (
        (primary_product.qty_inference_reason or "").strip()
        if primary_product and primary_product.qty_inference_reason
        else (summary.qtyInferenceReason or "")
    )
    detected = summary.detected_quantity
    final_q = corrected if corrected is not None else summary.qty
    updated: datetime = summary.updated_at
    return {
        "inventory_id": inventory.id,
        "inventory_name": inventory.name,
        "aisle_id": aisle.id,
        "aisle_name": aisle.code,
        "aisle_sequence": aisle_sequence,
        "position_id": position.id,
        "position_code": export_position_code(position),
        "sku": summary.sku or "",
        "product_label": product_label,
        "barcode": barcode_s,
        "internal_code": internal_s,
        "detected_quantity": "" if detected is None else detected,
        "corrected_quantity": "" if corrected is None else corrected,
        "final_quantity": final_q,
        "qty_source": qty_src,
        "qty_inference_reason": qty_reason,
        "position_status": summary.status,
        "traceability_status": summary.traceability_status or "",
        "has_evidence": summary.has_evidence,
        "source_image_id": summary.source_image_id or "",
        "primary_evidence_id": summary.primary_evidence_id or "",
        "needs_review": summary.needs_review,
        "updated_at": updated.isoformat(),
    }
