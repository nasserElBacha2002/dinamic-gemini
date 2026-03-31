"""Map consolidated positions to flat dict rows for CSV export.

Delegates quantity/traceability/summary semantics to ``position_to_summary`` (v3 API parity).
"""

from __future__ import annotations

import json
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
    return position_to_operational_export_row_dict(
        inventory,
        aisle,
        aisle_sequence,
        position,
        primary_product,
    )


def position_to_operational_export_row_dict(
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
    updated: datetime = summary.updated_at
    return {
        "inventory_id": inventory.id,
        "inventory_name": inventory.name,
        "aisle_id": aisle.id,
        "aisle_code": aisle.code,
        "aisle_sequence": aisle_sequence,
        "position_id": position.id,
        "position_status": summary.status,
        "needs_review": summary.needs_review,
        "position_code": export_position_code(position),
        "product_sku": summary.product.sku or summary.sku or "",
        "product_display_label": summary.product.display_label or "",
        "barcode": summary.product.barcode or "",
        "detected_quantity": summary.quantity.detected,
        "corrected_quantity": "" if corrected is None else corrected,
        "final_quantity": summary.quantity.final,
        "qty_source": summary.quantity.source,
        "qty_inference_reason": summary.quantity.inference_reason or "",
        "traceability_status": summary.traceability.status or "",
        "source_image_id": summary.traceability.source_image_id or "",
        "primary_evidence_id": summary.traceability.primary_evidence_id or "",
        "updated_at": updated.isoformat(),
    }


def position_to_technical_export_row_dict(
    inventory: Inventory,
    aisle: Aisle,
    aisle_sequence: int,
    position: Position,
) -> Dict[str, Any]:
    snap = _summary_dict(position)
    aggregated_raw = snap.get("aggregated_from_ids")
    aggregated_from_ids = (
        "|".join(str(v).strip() for v in aggregated_raw if isinstance(v, str) and str(v).strip())
        if isinstance(aggregated_raw, list)
        else ""
    )
    audit_raw = snap.get("_audit")
    audit_json = json.dumps(audit_raw, sort_keys=True, ensure_ascii=True) if isinstance(audit_raw, dict) else ""
    return {
        "inventory_id": inventory.id,
        "inventory_name": inventory.name,
        "aisle_id": aisle.id,
        "aisle_code": aisle.code,
        "aisle_sequence": aisle_sequence,
        "position_id": position.id,
        "position_code": export_position_code(position),
        "internal_code": (snap.get("internal_code") or "") if isinstance(snap.get("internal_code"), str) else "",
        "review_display_label": (
            (snap.get("review_display_label") or "") if isinstance(snap.get("review_display_label"), str) else ""
        ),
        "position_barcode": (
            (snap.get("position_barcode") or "") if isinstance(snap.get("position_barcode"), str) else ""
        ),
        "pallet_id": (snap.get("pallet_id") or "") if isinstance(snap.get("pallet_id"), str) else "",
        "entity_uid": (snap.get("entity_uid") or "") if isinstance(snap.get("entity_uid"), str) else "",
        "entity_type": (snap.get("entity_type") or "") if isinstance(snap.get("entity_type"), str) else "",
        "count_status": (snap.get("count_status") or "") if isinstance(snap.get("count_status"), str) else "",
        "raw_qty": "" if snap.get("raw_qty") is None else snap.get("raw_qty"),
        "qty_parse_status": (
            (snap.get("qty_parse_status") or "") if isinstance(snap.get("qty_parse_status"), str) else ""
        ),
        "qty_origin_field": (
            (snap.get("qty_origin_field") or "") if isinstance(snap.get("qty_origin_field"), str) else ""
        ),
        "aggregated_from_ids": aggregated_from_ids,
        "audit_json": audit_json,
        "updated_at": position.updated_at.isoformat(),
    }
