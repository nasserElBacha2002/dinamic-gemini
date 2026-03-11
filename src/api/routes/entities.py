"""Stage 2.1.E — Entities and review API (list, evidence, submit review, audit)."""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException

from pydantic import ValidationError

from src.api.schemas.requests import ReviewSubmitBody
from src.api.schemas.responses import (
    EntityAuditResponse,
    EntityEvidenceResponse,
    EntitiesListResponse,
    EntityListItem,
    ReviewSubmitResponse,
    TRACEABILITY_STATUS_VALUES,
    TraceabilitySummary,
)
from src.review import get_entity_audit, load_reviews, save_review
from src.review.review_merge import ACTIONS
from src.reporting.display_label import derive_review_display_label
from src.utils.validation import validate_entity_uid, validate_job_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/inventory/jobs", tags=["entities"])


def _resolve_report_and_run_dir(job_id: str) -> tuple[Path, Path]:
    """Resolve report path and run_dir for job_id. Avoids circular import by local use of job_store + config."""
    from src.api.routes.jobs import _resolve_report_and_run_dir as resolve

    return resolve(job_id)


def _load_report(report_path: Path) -> dict:
    with open(report_path, encoding="utf-8") as f:
        return json.load(f)


def _resolve_entity(report: dict, entity_uid_or_pallet_id: str) -> Optional[Dict[str, Any]]:
    """Return entity dict by entity_uid; if not found, by pallet_id if unique."""
    entities = report.get("entities") or []
    by_uid = {e.get("entity_uid"): e for e in entities if e.get("entity_uid")}
    if entity_uid_or_pallet_id in by_uid:
        return by_uid[entity_uid_or_pallet_id]
    by_pallet = [e for e in entities if (e.get("pallet_id") or "") == entity_uid_or_pallet_id]
    if len(by_pallet) == 1:
        return by_pallet[0]
    if len(by_pallet) > 1:
        raise HTTPException(400, "Multiple entities share this pallet_id; use entity_uid")
    return None


@router.get("/{job_id}/entities", response_model=EntitiesListResponse)
async def list_entities(
    job_id: str,
    status: Optional[str] = None,
    entity_type: Optional[str] = None,
    traceability_status: Optional[str] = None,
) -> EntitiesListResponse:
    """List entities from report. Optional filters: status, entity_type, traceability_status (Epic 3.1.C).

    traceability_summary, when present, is always the full-job summary (all entities in the report),
    regardless of filters. Invalid traceability_status filter value returns 422.

    Epic 5 — source_image_original_filename: Read from the report as-is. Only reports generated
    after Epic 5 (photos jobs with image metadata at report-build time) contain this field; legacy
    reports and video jobs do not. When absent in the report, the API returns null (no fallback).
    """
    try:
        job_id = validate_job_id(job_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if traceability_status is not None and traceability_status.strip():
        want = traceability_status.strip().lower()
        if want not in TRACEABILITY_STATUS_VALUES:
            raise HTTPException(
                status_code=422,
                detail=f"traceability_status must be one of: {', '.join(sorted(TRACEABILITY_STATUS_VALUES))}",
            )
    report_path, _run_dir = _resolve_report_and_run_dir(job_id)
    report = _load_report(report_path)
    full_entities = report.get("entities") or []
    entities = list(full_entities)
    if status is not None and status.strip():
        entities = [e for e in entities if (e.get("count_status") or "") == status.strip()]
    if entity_type is not None and entity_type.strip():
        entities = [e for e in entities if (e.get("entity_type") or "") == entity_type.strip()]
    if traceability_status is not None and traceability_status.strip():
        want = traceability_status.strip().lower()
        entities = [e for e in entities if (e.get("traceability_status") or "").lower() == want]
    # Epic 3.1.C: full-job summary only (from report or computed from full entity list)
    summary_dict = report.get("traceability_summary")
    if summary_dict is None and full_entities:
        from src.domain.traceability import compute_traceability_summary_from_entity_dicts
        summary_dict = compute_traceability_summary_from_entity_dicts(full_entities)
    summary_model = None
    if isinstance(summary_dict, dict):
        try:
            summary_model = TraceabilitySummary(**summary_dict)
        except ValidationError:
            if full_entities:
                from src.domain.traceability import compute_traceability_summary_from_entity_dicts
                summary_dict = compute_traceability_summary_from_entity_dicts(full_entities)
                summary_model = TraceabilitySummary(**summary_dict)
                logger.warning(
                    "Report traceability_summary invalid or malformed; recomputed from full entity list for job_id=%s",
                    job_id,
                )
    out: List[EntityListItem] = []
    for e in entities:
        raw_status = e.get("traceability_status")
        want = (raw_status or "").strip().lower()
        traceability_status_val = want if want in TRACEABILITY_STATUS_VALUES else None
        # Epic 3.1.D: single source of truth for display label (centralized derivation; empty/whitespace normalized)
        review_display_label = derive_review_display_label(
            e.get("internal_code"),
            e.get("position_barcode"),
        )
        # Epic 5: pass through from report; null for legacy reports or when not in report (no fallback).
        out.append(
            EntityListItem(
                entity_uid=str(e.get("entity_uid") or ""),
                pallet_id=e.get("pallet_id"),
                entity_type=str(e.get("entity_type") or ""),
                count_status=e.get("count_status"),
                entity_quality_score=e.get("entity_quality_score"),
                evidence_ref=e.get("evidence_path"),
                source_image_id=e.get("source_image_id"),
                traceability_status=traceability_status_val,
                traceability_warning=e.get("traceability_warning"),
                source_image_original_filename=e.get("source_image_original_filename"),
                review_display_label=review_display_label,
                product_display_label=review_display_label,  # backward-compat alias
            )
        )
    return EntitiesListResponse(entities=out, traceability_summary=summary_model)


@router.get("/{job_id}/entities/{entity_uid}/evidence", response_model=EntityEvidenceResponse)
async def get_entity_evidence(job_id: str, entity_uid: str) -> EntityEvidenceResponse:
    """Return evidence paths from evidence_index.json for the entity (by entity_uid or unique pallet_id)."""
    try:
        job_id = validate_job_id(job_id)
        entity_uid = validate_entity_uid(entity_uid)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    report_path, run_dir = _resolve_report_and_run_dir(job_id)
    index_path = run_dir / "evidence_index.json"
    if not index_path.exists():
        raise HTTPException(404, "Evidence index not found")
    with open(index_path, encoding="utf-8") as f:
        index = json.load(f)
    report = _load_report(report_path)
    entity = _resolve_entity(report, entity_uid)
    if not entity:
        raise HTTPException(404, "Entity not found")
    uid = entity.get("entity_uid")
    index_entities = index.get("entities") or []
    for ie in index_entities:
        if ie.get("entity_uid") == uid:
            return EntityEvidenceResponse(entity_uid=uid, evidence=ie.get("evidence") or {})
    return EntityEvidenceResponse(entity_uid=uid, evidence={})


def _build_review_event(
    action: str,
    before: dict,
    after: dict,
    actor: str,
    notes: Optional[str],
) -> dict:
    from datetime import datetime, timezone

    return {
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "actor": actor or "unknown",
        "action": action,
        "before": before,
        "after": after,
        "notes": notes,
    }


@router.post("/{job_id}/entities/{entity_uid}/review", response_model=ReviewSubmitResponse)
async def submit_review(job_id: str, entity_uid: str, body: ReviewSubmitBody) -> ReviewSubmitResponse:
    """Submit a manual review action. Actions: SET_COUNT, MARK_EMPTY, MARK_INVALID."""
    try:
        job_id = validate_job_id(job_id)
        entity_uid = validate_entity_uid(entity_uid)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    report_path, run_dir = _resolve_report_and_run_dir(job_id)
    report = _load_report(report_path)
    entity = _resolve_entity(report, entity_uid)
    if not entity:
        raise HTTPException(404, "Entity not found")
    uid = entity.get("entity_uid")
    action = (body.action or "").strip()
    if action not in ACTIONS:
        raise HTTPException(422, f"action must be one of: {', '.join(ACTIONS)}")
    if action == "SET_COUNT" and body.final_quantity is None:
        raise HTTPException(422, "final_quantity required for SET_COUNT")

    before = {
        "count_status": entity.get("count_status"),
        "final_quantity": entity.get("final_quantity"),
    }
    if action == "SET_COUNT":
        after = {"count_status": "COUNTED_MANUAL", "final_quantity": body.final_quantity}
    elif action == "MARK_EMPTY":
        after = {"count_status": "EMPTY", "final_quantity": 0}
    else:
        after = {"count_status": "INVALID_STRUCTURE", "final_quantity": None}

    # Apply any existing reviews so before reflects current effective state
    reviews = load_reviews(run_dir)
    ent_reviews = (reviews.get(uid) or {}).get("events") or []
    if ent_reviews:
        last = ent_reviews[-1]
        a = last.get("after")
        if isinstance(a, dict):
            before = {"count_status": a.get("count_status"), "final_quantity": a.get("final_quantity")}

    event = _build_review_event(action, before, after, body.actor or "", body.notes)
    save_review(run_dir, uid, event)
    return ReviewSubmitResponse(entity_uid=uid, action=action, message="Review saved")


@router.get("/{job_id}/entities/{entity_uid}/audit", response_model=EntityAuditResponse)
async def get_entity_audit_trail(job_id: str, entity_uid: str) -> EntityAuditResponse:
    """Return full audit trail (review events) for the entity."""
    try:
        job_id = validate_job_id(job_id)
        entity_uid = validate_entity_uid(entity_uid)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    report_path, run_dir = _resolve_report_and_run_dir(job_id)
    report = _load_report(report_path)
    entity = _resolve_entity(report, entity_uid)
    if not entity:
        raise HTTPException(404, "Entity not found")
    uid = entity.get("entity_uid")
    events = get_entity_audit(job_id, run_dir, uid)
    return EntityAuditResponse(entity_uid=uid, events=events)
