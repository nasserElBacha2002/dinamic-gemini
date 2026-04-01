"""Map consolidated positions to flat dict rows for CSV export.

The operational export is built from :class:`PositionCanonicalView` so it stays aligned with the
public contract (`product` / `quantity` / `traceability`) without depending on HTTP serializers.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from src.application.mappers.position_canonical_view import build_position_canonical_view
from src.domain.aisle.entities import Aisle
from src.domain.inventory.entities import Inventory
from src.domain.positions.entities import Position
from src.domain.products.entities import ProductRecord

_DIGIT_CHUNKS = re.compile(r"(\d+)")


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


def _safe_int(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        candidate = value.strip()
        if candidate and re.fullmatch(r"[+-]?\d+", candidate):
            return int(candidate)
    return None


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _natural_text_sort_key(text: str) -> Tuple[Tuple[int, int, str], ...]:
    normalized = _safe_str(text).lower()
    if not normalized:
        return ()
    parts: List[Tuple[int, int, str]] = []
    for chunk in _DIGIT_CHUNKS.split(normalized):
        if not chunk:
            continue
        if chunk.isdigit():
            parts.append((0, int(chunk), ""))
        else:
            parts.append((1, 0, chunk))
    return tuple(parts)


def _field_sort_key(value: Any) -> Tuple[int, int, int, Tuple[Tuple[int, int, str], ...]]:
    text = _safe_str(value)
    if not text:
        return (1, 1, 0, ())
    numeric = _safe_int(value)
    if numeric is not None:
        return (0, 0, numeric, ())
    return (0, 1, 0, _natural_text_sort_key(text))


def export_position_sort_key(p: Position) -> tuple:
    """Deterministic, type-safe ordering within an aisle after consolidation."""
    j = _summary_dict(p)
    return (
        *_field_sort_key(export_position_code(p)),
        *_field_sort_key(j.get("internal_code")),
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
    corrected = primary_product.corrected_quantity if primary_product is not None else None
    view = build_position_canonical_view(
        position,
        primary_product,
        corrected_quantity=corrected,
    )
    updated: datetime = position.updated_at
    return {
        "inventory_id": inventory.id,
        "inventory_name": inventory.name,
        "aisle_id": aisle.id,
        "aisle_code": aisle.code,
        "aisle_sequence": aisle_sequence,
        "position_id": position.id,
        "position_status": view.review.status,
        "needs_review": view.review.needs_review,
        "position_code": export_position_code(position),
        "product_sku": view.product.public_sku or "",
        "product_display_label": view.product.display_label or "",
        "barcode": view.product.barcode or "",
        "detected_quantity": view.quantity.detected_quantity,
        "corrected_quantity": "" if corrected is None else corrected,
        "final_quantity": view.quantity.final_display_quantity,
        "qty_source": view.quantity.qty_source,
        "qty_inference_reason": view.quantity.qty_inference_reason or "",
        "traceability_status": view.traceability.traceability_status or "",
        "source_image_id": view.traceability.source_image_id or "",
        "primary_evidence_id": view.review.primary_evidence_id or "",
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
