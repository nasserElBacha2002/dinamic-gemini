"""
Derived fields for Review Queue (Sprint 4.2).

Keeps list_review_queue free of API-layer helpers. Threshold aligns with
frontend `LOW_CONFIDENCE_THRESHOLD` (0.5) — single operational definition.
"""

from __future__ import annotations

from datetime import timezone
from typing import Any, Optional, Tuple

from src.application.constants.review_quality import LOW_CONFIDENCE_THRESHOLD
from src.domain.positions.entities import Position


def _parse_summary_quantity(raw: object) -> Optional[int]:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        try:
            v = int(raw)
            return v if v >= 0 else None
        except (TypeError, ValueError):
            return None
    if isinstance(raw, str) and raw.strip():
        try:
            v = int(raw.strip())
            return v if v >= 0 else None
        except (ValueError, TypeError):
            return None
    return None


def position_has_primary_evidence(position: Position) -> bool:
    return bool(position.primary_evidence_id and str(position.primary_evidence_id).strip())


def summary_sku_and_detected_quantity(position: Position) -> Tuple[Optional[str], int]:
    """SKU + quantity from detected_summary_json only (same rules as position list mapping)."""
    j: Any = position.detected_summary_json
    if not j or not isinstance(j, dict):
        return None, 0
    sku_raw = j.get("internal_code")
    sku: Optional[str] = None
    if sku_raw is not None and isinstance(sku_raw, str) and sku_raw.strip():
        sku = sku_raw.strip()
    if sku is None:
        fallback = j.get("review_display_label") or j.get("position_barcode") or j.get("pallet_id")
        if fallback is not None and isinstance(fallback, str) and fallback.strip():
            sku = fallback.strip()
    q_raw = j.get("final_quantity") if j.get("final_quantity") is not None else j.get("product_label_quantity")
    qty = _parse_summary_quantity(q_raw)
    return sku, qty if qty is not None else 0


def traceability_normalized(position: Position) -> str:
    j = position.detected_summary_json if isinstance(position.detected_summary_json, dict) else {}
    return str(j.get("traceability_status") or "").strip().lower()


def priority_tier(position: Position) -> int:
    """
    Explainable tiers (lower = review sooner), matching frontend deriveResultPriority:
    P1: needs_review AND (invalid traceability OR missing evidence)
    P2: needs_review AND (low confidence OR qty zero from summary json)
    P3: needs_review only
    P4: else
    """
    needs = position.needs_review
    invalid_trace = traceability_normalized(position) == "invalid"
    missing_ev = not position_has_primary_evidence(position)
    _, qty = summary_sku_and_detected_quantity(position)
    low_conf = position.confidence < LOW_CONFIDENCE_THRESHOLD
    qty0 = qty == 0
    if needs and (invalid_trace or missing_ev):
        return 1
    if needs and (low_conf or qty0):
        return 2
    if needs:
        return 3
    return 4


def updated_at_sort_ts(position: Position) -> float:
    dt = position.updated_at
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc).timestamp()
    return dt.timestamp()
