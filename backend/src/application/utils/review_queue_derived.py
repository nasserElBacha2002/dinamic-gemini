"""
Derived fields for Review Queue (Sprint 4.2).

Keeps list_review_queue free of API-layer helpers. Threshold aligns with
frontend `LOW_CONFIDENCE_THRESHOLD` (0.5) — single operational definition.
"""

from __future__ import annotations

from datetime import timezone

from src.application.constants.review_quality import LOW_CONFIDENCE_THRESHOLD
from src.application.mappers.position_canonical_view import build_position_canonical_view
from src.domain.positions.entities import Position
from src.domain.products.entities import ProductRecord


def position_has_primary_evidence(position: Position) -> bool:
    return bool(position.primary_evidence_id and str(position.primary_evidence_id).strip())


def summary_sku_and_detected_quantity(
    position: Position,
    primary_product: ProductRecord | None = None,
) -> tuple[str | None, int]:
    """Prefer canonical SKU/quantity; keep snapshot fallback for aggregated or legacy-only rows."""
    view = build_position_canonical_view(position, primary_product)
    sku = view.product.public_sku
    qty = int(view.quantity.final_display_quantity)
    return sku, qty


def traceability_normalized(
    position: Position,
    primary_product: ProductRecord | None = None,
) -> str:
    view = build_position_canonical_view(position, primary_product)
    return str(view.traceability.traceability_status or "").strip().lower()


def priority_tier(
    position: Position,
    primary_product: ProductRecord | None = None,
) -> int:
    """
    Explainable tiers (lower = review sooner), matching frontend deriveResultPriority:
    P1: needs_review AND (invalid traceability OR missing evidence)
    P2: needs_review AND (low confidence OR qty zero from canonical quantity)
    P3: needs_review only
    P4: else
    """
    needs = position.needs_review
    invalid_trace = traceability_normalized(position, primary_product) == "invalid"
    missing_ev = not position_has_primary_evidence(position)
    _, qty = summary_sku_and_detected_quantity(position, primary_product)
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
