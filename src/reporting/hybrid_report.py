"""
Stage 4 — Build deterministic hybrid report dict.

Standard report: report_version 2.1, mode hybrid_v2.1, summary block, entities.
Epic 3.1.C: traceability_summary block (counts by traceability status) for review/audit.
Traceability warning: report-only diagnostic (e.g. reason when status is invalid); not persisted to DB.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

from src.domain.entity import Entity
from src.domain.traceability import compute_traceability_summary
from src.reporting.display_label import derive_review_display_label


def _build_summary_from_entities(entities: List[Entity]) -> Dict[str, int]:
    """Compute summary counts from entity list (includes counted_manual)."""
    summary = {
        "total_entities": len(entities),
        "pallets": 0,
        "empty_pallets": 0,
        "loose_boxes": 0,
        "counted": 0,
        "needs_review": 0,
        "not_countable": 0,
        "invalid_structure": 0,
        "counted_manual": 0,
    }
    for e in entities:
        if e.entity_type == "PALLET":
            summary["pallets"] += 1
        elif e.entity_type == "EMPTY_PALLET":
            summary["empty_pallets"] += 1
        elif e.entity_type == "LOOSE_BOXES":
            summary["loose_boxes"] += 1
        if e.count_status == "COUNTED":
            summary["counted"] += 1
        elif e.count_status == "COUNTED_MANUAL":
            summary["counted_manual"] += 1
        elif e.count_status == "NEEDS_REVIEW":
            summary["needs_review"] += 1
        elif e.count_status == "NOT_COUNTABLE":
            summary["not_countable"] += 1
        elif e.count_status == "EMPTY":
            pass  # empty_pallets already counted by type
        elif e.count_status == "INVALID_STRUCTURE":
            summary["invalid_structure"] += 1
    return summary


def build_hybrid_report(
    video_path: str,
    entities: List[Entity],
    frames_selected: int,
    frame_indices: Optional[List[int]] = None,
) -> Dict[str, Any]:
    """Build the authoritative hybrid report (report_version 2.1, summary, entities).

    Args:
        video_path: Path to the source video.
        entities: List of Entity with count_status, final_quantity, entity_quality_score set.
        frames_selected: Number of representative frames sent to Gemini.
        frame_indices: Optional list of video frame indices (audit/debug).

    Returns:
        Report dict with report_version 2.1, mode hybrid_v2.1, summary, entities.
    """
    path_obj = Path(video_path)
    summary = _build_summary_from_entities(entities)

    entity_dicts = []
    for e in entities:
        entity_dicts.append({
            "entity_uid": e.entity_uid,
            "entity_type": e.entity_type,
            "model_entity_id": e.model_entity_id,
            "pallet_id": e.pallet_id,
            "pallet_id_method": e.pallet_id_method,
            "position_barcode": e.position_barcode,
            "position_label_bbox": e.position_label_bbox,
            "internal_code": e.internal_code,
            "product_label_quantity": e.product_label_quantity,
            "product_label_bbox": e.product_label_bbox,
            "has_boxes": e.has_boxes,
            "confidence": e.confidence,
            "count_status": e.count_status,
            "final_quantity": e.final_quantity,
            "conflict_flag": e.conflict_flag,
            "conflict_reason": e.conflict_reason,
            "entity_quality_score": e.entity_quality_score,
            "evidence_path": e.evidence_path,
            "evidence_localization": e.evidence_localization,
            # Epic 3.1.B: traceability (traceability_warning is report-only diagnostic, not persisted to pallet_results)
            "source_image_id": getattr(e, "source_image_id", None),
            "traceability_status": getattr(e, "traceability_status", None),
            "traceability_warning": getattr(e, "traceability_warning", None),
            # Epic 3.1.D: single review/export display label (internal_code else position_barcode; centralized derivation)
            "review_display_label": derive_review_display_label(e.internal_code, e.position_barcode),
        })

    report: Dict[str, Any] = {
        "report_version": "2.1",
        "mode": "hybrid_v2.1",
        "video": {"path": video_path, "name": path_obj.name},
        "frames_selected": frames_selected,
        "summary": summary,
        "traceability_summary": compute_traceability_summary(entities),
        "entities": entity_dicts,
    }
    if frame_indices is not None:
        report["frame_indices"] = frame_indices
    return report


