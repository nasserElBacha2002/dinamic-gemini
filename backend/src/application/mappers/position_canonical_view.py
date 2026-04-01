"""
Canonical read-model for assembling public position summaries (v3 — Sprint 1, cerrado).

Centralizes source-of-truth priority: ``ProductRecord`` (primary) over ``detected_summary_json``,
except for **aggregated** consolidated rows where the summary carries ``aggregated_from_ids`` and
authoritative totals today — see ADR ``docs/adr/inventory-v3-canonical-fields.md``.

``position_to_summary`` in :mod:`src.api.routes.v3.shared` maps this view to ``PositionSummaryResponse``
(incl. bloques Sprint 2) sin duplicar derivación en rutas. Traceability enrichment lives in
:mod:`src.application.services.position_traceability` (not in route helpers).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Literal, Optional, Tuple

from src.application.services.position_traceability import enrich_position_traceability_from_report
from src.domain.positions.entities import Position
from src.domain.products.entities import ProductRecord
from src.domain.quantity.resolution import (
    QtySource,
    has_strong_identity_for_qty_inference,
    is_product_present_for_qty_inference,
    normalize_raw_qty,
    resolve_final_qty,
)

# --- Quantity contract (matches public PositionSummaryResponse qty* semantics) ---
_QtySourcePublic = Literal[
    "detected",
    "inferred",
    "merge_inferred",
    "manual_review",
    "label_explicit",
    "unknown",
    "consolidated",
]
_QtyContract = Tuple[int, _QtySourcePublic, Optional[str], Optional[bool]]


def parse_summary_quantity(raw: object) -> Optional[int]:
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


def summary_sku_and_quantity_from_position(p: Position) -> tuple[Optional[str], int]:
    """SKU + quantity from ``detected_summary_json`` only (legacy / technical snapshot path)."""
    j = p.detected_summary_json
    if not j or not isinstance(j, dict):
        return None, 0
    sku_raw = j.get("internal_code")
    sku = None
    if sku_raw is not None and isinstance(sku_raw, str) and sku_raw.strip():
        sku = sku_raw.strip()
    if sku is None:
        fallback = (
            j.get("review_display_label")
            or j.get("position_barcode")
            or j.get("pallet_id")
        )
        if fallback is not None and isinstance(fallback, str) and fallback.strip():
            sku = fallback.strip()
    q_raw = j.get("final_quantity") if j.get("final_quantity") is not None else j.get("product_label_quantity")
    qty = parse_summary_quantity(q_raw)
    return sku, qty if qty is not None else 0


def qty_contract_from_product(primary: ProductRecord) -> _QtyContract:
    """Stable qty contract from authoritative ``ProductRecord``."""
    qty = max(0, primary.detected_quantity)
    src = (primary.qty_source or "").strip()
    if src == "inferred":
        return (qty, "inferred", primary.qty_inference_reason or None, True)
    if src == "merge_inferred":
        return (qty, "merge_inferred", None, True)
    if src == "manual_review":
        return (qty, "manual_review", None, True)
    if src == "label_explicit":
        return (qty, "label_explicit", None, True)
    if src in {"ocr", "llm_extracted", "fallback"}:
        return (qty, "detected", primary.qty_inference_reason or None, True)
    if src == "unknown":
        return (qty, "unknown", None, None)
    if src == "consolidated":
        return (qty, "consolidated", None, True)
    if src == "unresolved":
        return (0, "detected", None, False)
    return (qty, "detected", None, True)


def resolve_qty_contract_from_position_legacy(p: Position, *, has_evidence: bool) -> _QtyContract:
    """Legacy fallback when no ``ProductRecord`` — uses ``detected_summary_json`` only."""
    j = p.detected_summary_json if isinstance(p.detected_summary_json, dict) else {}

    qty_final = j.get("qty_final")
    qty_source = j.get("qty_source")
    qty_reason = j.get("qty_inference_reason")
    qty_is_resolved = j.get("qty_is_resolved")
    if isinstance(qty_final, int) and isinstance(qty_source, str) and qty_source.strip():
        api_source: Literal["detected", "inferred"] = (
            "inferred" if qty_source.strip() == QtySource.INFERRED.value else "detected"
        )
        resolved = qty_is_resolved if isinstance(qty_is_resolved, bool) else None
        return (int(qty_final), api_source, (str(qty_reason) if qty_reason is not None else None), resolved)

    if "final_quantity" in j:
        raw = j.get("final_quantity")
        present = True
    elif "product_label_quantity" in j:
        raw = j.get("product_label_quantity")
        present = True
    else:
        raw = None
        present = False
    normalized = normalize_raw_qty(raw, field_was_present=present)
    entity_type = (j.get("entity_type") or "").strip().upper()
    count_status = (j.get("count_status") or "").strip().upper()

    has_identity = has_strong_identity_for_qty_inference(
        internal_code=j.get("internal_code"),
        review_display_label=j.get("review_display_label"),
        position_barcode=j.get("position_barcode"),
        pallet_id=j.get("pallet_id"),
    )
    is_product_present = is_product_present_for_qty_inference(
        count_status=count_status,
        entity_type=entity_type,
        has_valid_evidence=has_evidence,
        has_identity=has_identity,
        traceability_status=j.get("traceability_status"),
    )
    allow_zero = entity_type == "EMPTY_PALLET"
    res = resolve_final_qty(
        has_valid_evidence=has_evidence,
        is_product_present=is_product_present,
        normalized_qty=normalized,
        allow_zero_as_valid=allow_zero,
    )
    api_source = "inferred" if res.qty_source == QtySource.INFERRED else "detected"
    return (res.qty_final, api_source, (res.qty_inference_reason.value if res.qty_inference_reason else None), res.is_resolved)


def _traceability_from_position(p: Position) -> tuple[Optional[str], Optional[str], Optional[str]]:
    summary_json = p.detected_summary_json if isinstance(p.detected_summary_json, dict) else {}
    source_image_id: Optional[str] = summary_json.get("source_image_id") or None
    traceability_status: Optional[str] = summary_json.get("traceability_status") or None
    source_image_original_filename: Optional[str] = summary_json.get("source_image_original_filename") or None
    if summary_json.get("entity_uid") and (
        source_image_id is None or traceability_status is None or source_image_original_filename is None
    ):
        # Lazy import avoids circular import with api.routes.v3.shared at module load.
        sid_from_report, ts_from_report, sof_from_report = enrich_position_traceability_from_report(p)
        if source_image_id is None and sid_from_report is not None:
            source_image_id = sid_from_report
        if traceability_status is None and ts_from_report is not None:
            traceability_status = ts_from_report
        if source_image_original_filename is None and sof_from_report is not None:
            source_image_original_filename = sof_from_report
    return source_image_id, traceability_status, source_image_original_filename


IdentitySource = Literal["primary_product", "summary_technical", "summary_aggregated"]


def _effective_corrected_quantity(
    corrected_quantity: Optional[int],
    primary_product: Optional[ProductRecord],
) -> Optional[int]:
    """Prefer explicit ``corrected_quantity`` from ``position_to_summary``; else primary row."""
    if corrected_quantity is not None:
        return corrected_quantity
    if primary_product is not None:
        return primary_product.corrected_quantity
    return None


def _canonical_display_label(
    technical_snapshot: Optional[Dict[str, Any]],
    primary_product: Optional[ProductRecord],
) -> Optional[str]:
    """Operator-facing label: primary ``description`` when non-empty; else ``review_display_label`` from snapshot."""
    if primary_product is not None:
        d = (primary_product.description or "").strip()
        if d:
            return d
    snap = technical_snapshot if isinstance(technical_snapshot, dict) else {}
    rdl = snap.get("review_display_label")
    if isinstance(rdl, str) and rdl.strip():
        return rdl.strip()
    return None


def _canonical_barcode(technical_snapshot: Optional[Dict[str, Any]]) -> Optional[str]:
    """``position_barcode`` from technical snapshot when present (no inference)."""
    snap = technical_snapshot if isinstance(technical_snapshot, dict) else {}
    b = snap.get("position_barcode")
    if isinstance(b, str) and b.strip():
        return b.strip()
    return None


def _final_display_quantity(corrected_quantity: Optional[int], system_qty: int) -> int:
    """Operator-visible line quantity: correction when set, else system-resolved qty (CSV ``final_quantity`` rule)."""
    if corrected_quantity is not None:
        return max(0, int(corrected_quantity))
    return int(system_qty)


@dataclass(frozen=True)
class PositionCanonicalProduct:
    """Product identity for public summary assembly.

    ``display_label`` and ``barcode`` are resolved here so HTTP assembly only reads the view
    (Sprint 2 — no extra ``primary_product`` pass-through in :func:`position_to_summary`).
    """

    primary_product_id: Optional[str]
    public_sku: Optional[str]
    identity_source: IdentitySource
    display_label: Optional[str]
    barcode: Optional[str]


@dataclass(frozen=True)
class PositionCanonicalQuantity:
    """Resolved quantity contract (public-facing).

    ``corrected_quantity`` is the operator correction (``ProductRecord.corrected_quantity``),
    threaded through the canonical view so ``PositionSummaryResponse`` is assembled from one place.
    """

    qty: int
    qty_source: _QtySourcePublic
    qty_inference_reason: Optional[str]
    qty_resolved: Optional[bool]
    detected_quantity: int
    is_aggregated: bool
    corrected_quantity: Optional[int]
    final_display_quantity: int


@dataclass(frozen=True)
class PositionCanonicalTraceability:
    source_image_id: Optional[str]
    traceability_status: Optional[str]
    source_image_original_filename: Optional[str]


@dataclass(frozen=True)
class PositionCanonicalReview:
    status: str
    review_resolution: Optional[str]
    needs_review: bool
    primary_evidence_id: Optional[str]
    has_evidence: bool


def resolve_effective_position_code(p: Position) -> str:
    """Authority for calculating the effective position_code (Sprint 4.5 refined).

    Priority:
    1. Corrected position code from domain entity.
    2. pallet_id from detected_summary_json.
    3. position_barcode from detected_summary_json.
    4. entity_uid from detected_summary_json.
    5. Fallback: position identity (p.id).
    """
    if p.corrected_position_code is not None and str(p.corrected_position_code).strip() != "":
        return str(p.corrected_position_code).strip()

    j = p.detected_summary_json if isinstance(p.detected_summary_json, dict) else {}
    for k in ("pallet_id", "position_barcode", "entity_uid"):
        v = j.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()

    return p.id


@dataclass(frozen=True)
class PositionCanonicalView:
    """Intermediate canonical layer before ``PositionSummaryResponse``.

    ``technical_snapshot`` is the raw ``detected_summary_json`` dict when present (pipeline /
    consolidation snapshot); the HTTP response still echoes it separately for backward compatibility.
    """

    product: PositionCanonicalProduct
    quantity: PositionCanonicalQuantity
    traceability: PositionCanonicalTraceability
    review: PositionCanonicalReview
    position_code: str
    technical_snapshot: Optional[Dict[str, Any]]


def build_position_canonical_view(
    p: Position,
    primary_product: Optional[ProductRecord] = None,
    *,
    corrected_quantity: Optional[int] = None,
) -> PositionCanonicalView:
    """Build :class:`PositionCanonicalView` with explicit source priority (ADR + plan Sprint 1)."""
    effective_corrected = _effective_corrected_quantity(corrected_quantity, primary_product)
    summary_json = p.detected_summary_json if isinstance(p.detected_summary_json, dict) else {}
    has_evidence = bool(
        p.primary_evidence_id is not None and str(p.primary_evidence_id).strip() != ""
    )
    aggregated_raw = summary_json.get("aggregated_from_ids")
    is_aggregated = isinstance(aggregated_raw, list) and len(aggregated_raw) > 0

    trace = _traceability_from_position(p)
    traceability = PositionCanonicalTraceability(
        source_image_id=trace[0],
        traceability_status=trace[1],
        source_image_original_filename=trace[2],
    )
    pos_code = resolve_effective_position_code(p)
    review = PositionCanonicalReview(
        status=p.status.value,
        review_resolution=(
            p.review_resolution.value
            if p.review_resolution is not None
            else None
        ),
        needs_review=p.needs_review,
        primary_evidence_id=p.primary_evidence_id,
        has_evidence=has_evidence,
    )
    snap = p.detected_summary_json if isinstance(p.detected_summary_json, dict) else None

    summary_sku, summary_detected_qty = summary_sku_and_quantity_from_position(p)

    if is_aggregated:
        raw_q = summary_json.get("final_quantity")
        try:
            qty = max(0, int(raw_q))
        except (TypeError, ValueError):
            qty = 0
        quantity = PositionCanonicalQuantity(
            qty=qty,
            qty_source="consolidated",
            qty_inference_reason=None,
            qty_resolved=True,
            detected_quantity=qty,
            is_aggregated=True,
            corrected_quantity=effective_corrected,
            final_display_quantity=_final_display_quantity(effective_corrected, qty),
        )
        product = PositionCanonicalProduct(
            primary_product_id=(primary_product.id if primary_product is not None else None),
            public_sku=summary_sku,
            identity_source="summary_aggregated",
            display_label=_canonical_display_label(snap, primary_product),
            barcode=_canonical_barcode(snap),
        )
        return PositionCanonicalView(
            product=product,
            quantity=quantity,
            traceability=traceability,
            review=review,
            position_code=pos_code,
            technical_snapshot=snap,
        )

    if primary_product is not None:
        src = (primary_product.qty_source or "").strip()
        if src:
            qty, qty_source, qty_reason, qty_resolved = qty_contract_from_product(primary_product)
        else:
            qty = max(0, primary_product.detected_quantity)
            qty_source = "detected"
            qty_reason = None
            qty_resolved = None
        detected_quantity = qty
        rec_sku = primary_product.sku
        sku_display = str(rec_sku).strip() if rec_sku is not None and str(rec_sku).strip() != "" else summary_sku
        product = PositionCanonicalProduct(
            primary_product_id=primary_product.id,
            public_sku=sku_display,
            identity_source="primary_product",
            display_label=_canonical_display_label(snap, primary_product),
            barcode=_canonical_barcode(snap),
        )
        quantity = PositionCanonicalQuantity(
            qty=qty,
            qty_source=qty_source,
            qty_inference_reason=qty_reason,
            qty_resolved=qty_resolved,
            detected_quantity=detected_quantity,
            is_aggregated=False,
            corrected_quantity=effective_corrected,
            final_display_quantity=_final_display_quantity(effective_corrected, qty),
        )
        return PositionCanonicalView(
            product=product,
            quantity=quantity,
            traceability=traceability,
            review=review,
            position_code=pos_code,
            technical_snapshot=snap,
        )

    qty, qty_source, qty_reason, qty_resolved = resolve_qty_contract_from_position_legacy(p, has_evidence=has_evidence)
    product = PositionCanonicalProduct(
        primary_product_id=None,
        public_sku=summary_sku,
        identity_source="summary_technical",
        display_label=_canonical_display_label(snap, None),
        barcode=_canonical_barcode(snap),
    )
    quantity = PositionCanonicalQuantity(
        qty=qty,
        qty_source=qty_source,
        qty_inference_reason=qty_reason,
        qty_resolved=qty_resolved,
        detected_quantity=summary_detected_qty,
        is_aggregated=False,
        corrected_quantity=effective_corrected,
        final_display_quantity=_final_display_quantity(effective_corrected, qty),
    )
    return PositionCanonicalView(
        product=product,
        quantity=quantity,
        traceability=traceability,
        review=review,
        position_code=pos_code,
        technical_snapshot=snap,
    )
