"""
Map hybrid_report.json (pipeline output) to v3 domain entities — Épica 6.

One report entity (pallet/position) → one Position, one ProductRecord, one Evidence.
Evidence storage_path is relative to output root (job_id/run_id/evidence_path).
Strict mapping: missing or invalid values are recorded in detected_summary for audit;
we do not silently fabricate data. Use explicit sentinels (e.g. UNKNOWN, no_artifact)
where the model requires a value.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List
from uuid import uuid4

from src.domain.evidence.entities import Evidence, EvidenceType
from src.domain.labels.entities import RawLabel
from src.domain.positions.entities import Position, PositionStatus
from src.domain.products.entities import ProductRecord
from src.domain.quantity.resolution import (
    QtyParseStatus,
    QtySource,
    has_strong_identity_for_qty_inference,
    is_product_present_for_qty_inference,
    normalize_raw_qty,
    resolve_final_qty,
)

logger = logging.getLogger(__name__)

# Explicit sentinels when pipeline does not provide a value (auditable).
SKU_UNKNOWN = "UNKNOWN"
EVIDENCE_PATH_NO_ARTIFACT = "no_artifact"
_ACCEPTED_COUNT_STATUSES = frozenset({"COUNTED", "COUNTED_MANUAL"})


@dataclass
class MappedAisleResult:
    """Result of mapping a hybrid report to v3 domain for one aisle. v3.2.3: includes raw_labels."""
    positions: List[Position]
    product_records: List[ProductRecord]
    evidences: List[Evidence]
    raw_labels: List[RawLabel]


def _needs_review_from_entity(entity: Dict[str, Any]) -> bool:
    status = (entity.get("count_status") or "").strip().upper()
    return status in ("NEEDS_REVIEW", "NOT_COUNTABLE", "INVALID_STRUCTURE") or status == ""


def _confidence_from_entity(entity: Dict[str, Any]) -> tuple[float, bool]:
    """Return (confidence, confidence_was_missing). Missing or invalid -> 0.0 and needs_review."""
    raw = entity.get("confidence")
    if raw is None:
        return 0.0, True
    try:
        v = float(raw)
        return max(0.0, min(1.0, v)), False
    except (TypeError, ValueError):
        return 0.0, True


def _detected_summary(entity: Dict[str, Any], audit: Dict[str, Any]) -> Dict[str, Any]:
    """Build detected_summary_json for traceability; include audit flags for missing/invalid data.

    Includes position_barcode and review_display_label so the list API can show a sku fallback
    when internal_code is missing (aligns with derive_review_display_label: internal_code else position_barcode).
    """
    out = {
        "entity_uid": entity.get("entity_uid"),
        "entity_type": entity.get("entity_type"),
        "pallet_id": entity.get("pallet_id"),
        "internal_code": entity.get("internal_code"),
        "final_quantity": entity.get("final_quantity"),
        "product_label_quantity": entity.get("product_label_quantity"),
        "count_status": entity.get("count_status"),
    }
    # Fallback display fields for list API when internal_code is null (see BUG_INVESTIGATION_POSITIONS_SKU_QUANTITY_NULL).
    pos_barcode = entity.get("position_barcode")
    if pos_barcode is not None:
        out["position_barcode"] = pos_barcode if isinstance(pos_barcode, str) else str(pos_barcode)
    rdl = entity.get("review_display_label")
    if rdl is not None:
        out["review_display_label"] = rdl if isinstance(rdl, str) else str(rdl)
    # Epic 3.1.B: expose in position so API/frontend can show source image and traceability status
    sid = entity.get("source_image_id")
    if sid is not None:
        out["source_image_id"] = sid if isinstance(sid, str) else str(sid)
    ts = entity.get("traceability_status")
    if ts is not None:
        out["traceability_status"] = ts if isinstance(ts, str) else str(ts)
    # Epic 2 / Epic 5: persist so position API can expose source_image_original_filename at top level
    sof = entity.get("source_image_original_filename")
    if sof is not None and isinstance(sof, str) and sof.strip():
        out["source_image_original_filename"] = sof.strip()
    if audit:
        out["_audit"] = audit
    return out


def _qty_from_entity(entity: Dict[str, Any], *, has_valid_evidence: bool) -> tuple[int, Dict[str, Any]]:
    """Resolve final qty + provenance for one report entity (v3.2.2).

    Returns (qty_final, qty_meta_for_summary_json).
    """
    # Prefer final_quantity field if present (pipeline-derived), else product_label_quantity.
    if "final_quantity" in entity:
        raw = entity.get("final_quantity")
        present = True
        origin = "final_quantity"
    elif "product_label_quantity" in entity:
        raw = entity.get("product_label_quantity")
        present = True
        origin = "product_label_quantity"
    else:
        raw = None
        present = False
        origin = "missing"

    normalized = normalize_raw_qty(raw, field_was_present=present)

    entity_type = (entity.get("entity_type") or "").strip().upper()
    count_status = (entity.get("count_status") or "").strip().upper()

    has_identity = has_strong_identity_for_qty_inference(
        internal_code=entity.get("internal_code"),
        review_display_label=entity.get("review_display_label"),
        position_barcode=entity.get("position_barcode"),
        pallet_id=entity.get("pallet_id"),
    )

    # Shared product-present rule for qty inference (mapper + API legacy) via shared helpers.
    is_product_present = is_product_present_for_qty_inference(
        count_status=count_status,
        entity_type=entity_type,
        has_valid_evidence=has_valid_evidence,
        has_identity=has_identity,
        traceability_status=entity.get("traceability_status"),
    )
    allow_zero = entity_type == "EMPTY_PALLET"

    res = resolve_final_qty(
        has_valid_evidence=has_valid_evidence,
        is_product_present=is_product_present,
        normalized_qty=normalized,
        allow_zero_as_valid=allow_zero,
    )
    if logger.isEnabledFor(logging.DEBUG) and res.qty_source == QtySource.INFERRED:
        logger.debug(
            "v3.2.2 qty inferred: entity_uid=%s count_status=%s entity_type=%s raw=%r parse=%s -> qty=%d",
            entity.get("entity_uid"),
            count_status,
            entity_type,
            raw,
            res.qty_parse_status.value,
            res.qty_final,
        )

    # Persist source as "unresolved" when not resolved so API/audit can distinguish from valid 0.
    # Semantic hardening: when quantity is explicit and parsed positive from label-oriented fields,
    # persist a specific authoritative source instead of generic "detected".
    source_value = "unresolved" if not res.is_resolved else res.qty_source.value
    if (
        res.is_resolved
        and normalized.parse_status == QtyParseStatus.VALID_POSITIVE
        and origin in {"final_quantity", "product_label_quantity"}
        and res.qty_source == QtySource.DETECTED
    ):
        source_value = "label_explicit"
    meta = {
        # Secondary projection in detected_summary_json; ProductRecord is authoritative.
        "qty_final": res.qty_final,
        "qty_source": source_value,
        "qty_inference_reason": res.qty_inference_reason.value if res.qty_inference_reason else None,
        "raw_qty": res.raw_qty,
        "qty_parse_status": res.qty_parse_status.value,
        "qty_origin_field": origin,
        "qty_is_resolved": res.is_resolved,
    }
    return res.qty_final, meta


def map_hybrid_report_to_domain(
    aisle_id: str,
    report: Dict[str, Any],
    run_dir: Path,
    run_id: str,
    job_id: str,
    now: datetime,
    inventory_id: str = "",
) -> MappedAisleResult:
    """
    Map hybrid_report entities to Position, ProductRecord, Evidence, and RawLabel (v3.2.3).

    run_dir: pipeline run directory (e.g. output_path/job_id/run_id).
    Storage paths for evidence are stored as relative to output root: job_id/run_id/evidence_path.
    inventory_id: required for raw_labels scope when provided.
    """
    positions: List[Position] = []
    product_records: List[ProductRecord] = []
    evidences: List[Evidence] = []
    raw_labels: List[RawLabel] = []

    entities = report.get("entities") or []
    for entity in entities:
        position_id = str(uuid4())
        product_id = str(uuid4())
        evidence_id = str(uuid4())

        confidence, confidence_missing = _confidence_from_entity(entity)
        needs_review = _needs_review_from_entity(entity) or confidence_missing

        evidence_path_rel = (entity.get("evidence_path") or "").strip()
        if evidence_path_rel:
            storage_path = f"{job_id}/{run_id}/{evidence_path_rel}"
            evidence_path_missing = False
        else:
            storage_path = EVIDENCE_PATH_NO_ARTIFACT
            evidence_path_missing = True
        # v3.2.2: Temporary proxy for "valid evidence". Better signal would be explicit
        # evidence validation; for this release we use presence of evidence_path.
        has_valid_evidence = not evidence_path_missing

        internal_code_raw = entity.get("internal_code")
        if internal_code_raw is not None and isinstance(internal_code_raw, str) and internal_code_raw.strip():
            sku = internal_code_raw.strip()
        else:
            sku = SKU_UNKNOWN
        internal_code_missing = sku == SKU_UNKNOWN

        quantity, qty_meta = _qty_from_entity(entity, has_valid_evidence=has_valid_evidence)
        # "Explicit" quantity missing = raw field absent/null/invalid (not "final quantity unavailable").
        explicit_quantity_missing = qty_meta.get("qty_parse_status") in (
            "missing",
            "null",
            "invalid",
        )

        audit: Dict[str, Any] = {}
        if confidence_missing:
            audit["confidence_missing"] = True
        if internal_code_missing:
            audit["internal_code_missing"] = True
        if explicit_quantity_missing:
            audit["explicit_quantity_missing"] = True
        if evidence_path_missing:
            audit["evidence_path_missing"] = True

        position = Position(
            id=position_id,
            aisle_id=aisle_id,
            status=PositionStatus.DETECTED,
            confidence=confidence,
            needs_review=needs_review,
            primary_evidence_id=evidence_id,
            created_at=now,
            updated_at=now,
            detected_summary_json={**_detected_summary(entity, audit), **qty_meta},
            corrected_summary_json=None,
        )
        positions.append(position)

        # ProductRecord is the authoritative persisted record for qty and provenance.
        product = ProductRecord(
            id=product_id,
            position_id=position_id,
            sku=sku,
            description="",
            detected_quantity=quantity,
            confidence=confidence,
            created_at=now,
            updated_at=now,
            corrected_quantity=None,
            qty_source=str(qty_meta.get("qty_source") or ""),
            qty_inference_reason=qty_meta.get("qty_inference_reason"),
            raw_qty=qty_meta.get("raw_qty"),
            qty_parse_status=qty_meta.get("qty_parse_status"),
        )
        product_records.append(product)

        evidence = Evidence(
            id=evidence_id,
            entity_type="position",
            entity_id=position_id,
            type=EvidenceType.POSITION_CROP,
            storage_path=storage_path,
            source_asset_id=None,
            is_primary=True,
            frame_index=None,
            timestamp_ms=None,
            bbox_json=None,
            quality_score=entity.get("entity_quality_score"),
        )
        evidences.append(evidence)

        # v3.2.3: one RawLabel per entity for normalization/merge layer
        raw_label_id = str(uuid4())
        entity_uid = entity.get("entity_uid") or position_id
        evidence_path_rel = (entity.get("evidence_path") or "").strip()
        group_key = f"position:{position_id}:evidence:{evidence_id}" if evidence_id else str(entity_uid)
        sku_raw = internal_code_raw if internal_code_raw is not None and isinstance(internal_code_raw, str) else None
        raw_labels.append(
            RawLabel(
                id=raw_label_id,
                inventory_id=inventory_id or "",
                aisle_id=aisle_id,
                position_id=position_id,
                evidence_id=evidence_id,
                group_key=group_key,
                provider="pipeline",
                source_type="hybrid_report",
                source_reference=entity.get("entity_uid"),
                sku_raw=sku_raw.strip() if sku_raw and sku_raw.strip() else None,
                sku_candidate=sku_raw.strip() if sku_raw and sku_raw.strip() else None,
                product_name_raw=entity.get("review_display_label") if isinstance(entity.get("review_display_label"), str) else None,
                detected_text=entity.get("internal_code") if isinstance(entity.get("internal_code"), str) else None,
                confidence=confidence,
                metadata={"entity_uid": entity_uid, "evidence_path": evidence_path_rel},
                created_at=now,
            )
        )

    return MappedAisleResult(
        positions=positions,
        product_records=product_records,
        evidences=evidences,
        raw_labels=raw_labels,
    )
