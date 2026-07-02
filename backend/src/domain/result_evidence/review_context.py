"""Operator review context for unlabeled / unconfirmed traceability outcomes."""

from __future__ import annotations

from src.domain.positions.entities import Position
from src.domain.result_evidence.entities import ResultEvidenceRecord

REVIEW_CONTEXT_OUTCOMES = frozenset({"no_readable_label"})

REVIEW_CONTEXT_TRACEABILITY_UNCONFIRMED_WARNING = (
    "Scan image shown for operator review; entity-level traceability is not confirmed."
)


def position_qualifies_for_review_context(position: Position) -> bool:
    """True when the operator should see the job scan image without validated entity evidence."""
    snap = position.detected_summary_json if isinstance(position.detected_summary_json, dict) else {}
    outcome = snap.get("detection_outcome")
    if isinstance(outcome, str) and outcome.strip() in REVIEW_CONTEXT_OUTCOMES:
        return True
    uid = snap.get("entity_uid")
    return isinstance(uid, str) and uid.strip().endswith("_no_readable_label")


def resolve_review_context_asset_id(
    position: Position,
    record: ResultEvidenceRecord | None,
    job_rows: list[ResultEvidenceRecord],
    assets_by_id: dict[str, object],
) -> str | None:
    """Resolve a job/aisle source asset for review preview (not validated entity evidence)."""
    if record is not None:
        persisted = (record.source_asset_id or "").strip()
        if persisted and persisted in assets_by_id:
            return persisted
        sid = (record.source_image_id or "").strip()
        if sid and sid in assets_by_id:
            return sid

    snap = position.detected_summary_json if isinstance(position.detected_summary_json, dict) else {}
    snap_sid = snap.get("source_image_id")
    if isinstance(snap_sid, str):
        sid = snap_sid.strip()
        if sid and sid in assets_by_id:
            return sid

    for row in job_rows:
        aid = (row.source_asset_id or "").strip()
        if aid and aid in assets_by_id:
            return aid
        sid = (row.source_image_id or "").strip()
        if sid and sid in assets_by_id:
            return sid

    if len(assets_by_id) == 1:
        return next(iter(assets_by_id))
    return None
