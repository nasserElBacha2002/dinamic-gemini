"""
Map hybrid_report.json (pipeline output) to v3 domain entities — Épica 6.

One report entity (pallet/position) → one Position, one ProductRecord, one Evidence.
Evidence storage_path is relative to output root (job_id/run_id/evidence_path).
Strict mapping: missing or invalid values are recorded in detected_summary for audit;
we do not silently fabricate data. Use explicit sentinels (e.g. UNKNOWN, no_artifact)
where the model requires a value.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List
from uuid import uuid4

from src.domain.evidence.entities import Evidence, EvidenceType
from src.domain.positions.entities import Position, PositionStatus
from src.domain.products.entities import ProductRecord

# Explicit sentinels when pipeline does not provide a value (auditable).
SKU_UNKNOWN = "UNKNOWN"
EVIDENCE_PATH_NO_ARTIFACT = "no_artifact"


@dataclass
class MappedAisleResult:
    """Result of mapping a hybrid report to v3 domain for one aisle."""
    positions: List[Position]
    product_records: List[ProductRecord]
    evidences: List[Evidence]


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
    """Build detected_summary_json for traceability; include audit flags for missing/invalid data."""
    out = {
        "entity_uid": entity.get("entity_uid"),
        "entity_type": entity.get("entity_type"),
        "pallet_id": entity.get("pallet_id"),
        "internal_code": entity.get("internal_code"),
        "final_quantity": entity.get("final_quantity"),
        "product_label_quantity": entity.get("product_label_quantity"),
        "count_status": entity.get("count_status"),
    }
    # Epic 3.1.B: expose in position so API/frontend can show source image and traceability status
    sid = entity.get("source_image_id")
    if sid is not None:
        out["source_image_id"] = sid if isinstance(sid, str) else str(sid)
    ts = entity.get("traceability_status")
    if ts is not None:
        out["traceability_status"] = ts if isinstance(ts, str) else str(ts)
    if audit:
        out["_audit"] = audit
    return out


def map_hybrid_report_to_domain(
    aisle_id: str,
    report: Dict[str, Any],
    run_dir: Path,
    run_id: str,
    job_id: str,
    now: datetime,
) -> MappedAisleResult:
    """
    Map hybrid_report entities to Position, ProductRecord, Evidence.

    run_dir: pipeline run directory (e.g. output_path/job_id/run_id).
    Storage paths for evidence are stored as relative to output root: job_id/run_id/evidence_path.
    """
    positions: List[Position] = []
    product_records: List[ProductRecord] = []
    evidences: List[Evidence] = []

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

        internal_code_raw = entity.get("internal_code")
        if internal_code_raw is not None and isinstance(internal_code_raw, str) and internal_code_raw.strip():
            sku = internal_code_raw.strip()
        else:
            sku = SKU_UNKNOWN
        internal_code_missing = sku == SKU_UNKNOWN

        final_qty = entity.get("final_quantity")
        product_qty = entity.get("product_label_quantity")
        if final_qty is not None and isinstance(final_qty, (int, float)):
            quantity = int(final_qty)
        elif product_qty is not None and isinstance(product_qty, (int, float)):
            quantity = int(product_qty)
        else:
            quantity = 0
        quantity_missing = (final_qty is None and product_qty is None) or quantity < 0
        quantity = max(0, quantity)

        audit: Dict[str, Any] = {}
        if confidence_missing:
            audit["confidence_missing"] = True
        if internal_code_missing:
            audit["internal_code_missing"] = True
        if quantity_missing:
            audit["quantity_missing"] = True
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
            detected_summary_json=_detected_summary(entity, audit),
            corrected_summary_json=None,
        )
        positions.append(position)

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

    return MappedAisleResult(
        positions=positions,
        product_records=product_records,
        evidences=evidences,
    )
