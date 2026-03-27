"""
Pure helpers for analytics — shared by in-memory repository and tests.

LOW_CONFIDENCE_THRESHOLD matches review_queue_derived / frontend reviewThresholds.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence, Tuple

from src.application.dto.analytics_dto import AnalyticsFilters
from src.application.utils.review_queue_derived import (
    LOW_CONFIDENCE_THRESHOLD,
    position_has_primary_evidence,
    summary_sku_and_detected_quantity,
    traceability_normalized,
)
from src.domain.jobs.entities import Job, JobStatus
from src.domain.positions.entities import Position, PositionStatus
from src.domain.reviews.entities import ReviewAction, ReviewActionType


def day_span_inclusive(date_from: Optional[datetime], date_to: Optional[datetime]) -> int:
    if date_from is None or date_to is None:
        return 1
    df = date_from.date()
    dt = date_to.date()
    return max(1, (dt - df).days + 1)


def _ts_in_range(ts: datetime, date_from: Optional[datetime], date_to: Optional[datetime]) -> bool:
    t = ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
    if date_from is not None:
        f = date_from if date_from.tzinfo else date_from.replace(tzinfo=timezone.utc)
        if t < f:
            return False
    if date_to is not None:
        e = date_to if date_to.tzinfo else date_to.replace(tzinfo=timezone.utc)
        if t > e:
            return False
    return True


def position_in_scope(
    pos: Position,
    aisle_id: str,
    inventory_id: str,
    aisle_to_inventory: Dict[str, str],
    filters: AnalyticsFilters,
) -> bool:
    if filters.inventory_id and inventory_id != filters.inventory_id:
        return False
    if filters.aisle_id and aisle_id != filters.aisle_id:
        return False
    if filters.date_from or filters.date_to:
        if not _ts_in_range(pos.updated_at, filters.date_from, filters.date_to):
            return False
    return True


def active_position(pos: Position) -> bool:
    return pos.status != PositionStatus.DELETED


def is_invalid_traceability(pos: Position) -> bool:
    return traceability_normalized(pos) == "invalid"


def is_low_confidence(pos: Position) -> bool:
    return pos.confidence < LOW_CONFIDENCE_THRESHOLD


def settling_action(ra: ReviewAction) -> bool:
    return ra.action_type in (
        ReviewActionType.CONFIRM,
        ReviewActionType.UPDATE_QUANTITY,
        ReviewActionType.UPDATE_SKU,
    )


def correction_action(ra: ReviewAction) -> bool:
    return ra.action_type in (ReviewActionType.UPDATE_QUANTITY, ReviewActionType.UPDATE_SKU)


def review_action_in_period(
    ra: ReviewAction,
    date_from: Optional[datetime],
    date_to: Optional[datetime],
) -> bool:
    return _ts_in_range(ra.created_at, date_from, date_to)


def aggregate_settling_metrics(
    actions: Sequence[ReviewAction],
    date_from: Optional[datetime],
    date_to: Optional[datetime],
) -> Tuple[int, int, int]:
    """Returns (settling_count, confirm_count, correction_count) in period."""
    settling = 0
    confirms = 0
    corrections = 0
    for ra in actions:
        if not review_action_in_period(ra, date_from, date_to):
            continue
        if settling_action(ra):
            settling += 1
            if ra.action_type == ReviewActionType.CONFIRM:
                confirms += 1
            if correction_action(ra):
                corrections += 1
    return settling, confirms, corrections


def compute_average_review_time_seconds(
    positions: Dict[str, Position],
    actions: Sequence[ReviewAction],
    date_from: Optional[datetime],
    date_to: Optional[datetime],
) -> Optional[float]:
    """First settling action per position in period; average lag from position.created_at."""
    first_ts: Dict[str, datetime] = {}
    for ra in sorted(actions, key=lambda x: (x.created_at, x.id)):
        if not review_action_in_period(ra, date_from, date_to) or not settling_action(ra):
            continue
        pid = ra.position_id
        if pid not in first_ts:
            first_ts[pid] = ra.created_at
    deltas: List[float] = []
    for pid, ts in first_ts.items():
        pos = positions.get(pid)
        if pos is None or not active_position(pos):
            continue
        p_created = pos.created_at if pos.created_at.tzinfo else pos.created_at.replace(tzinfo=timezone.utc)
        r_ts = ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
        deltas.append(max(0.0, (r_ts - p_created).total_seconds()))
    if not deltas:
        return None
    return sum(deltas) / len(deltas)


def compute_processing_success_rate(
    jobs: Sequence[Job],
    date_from: Optional[datetime],
    date_to: Optional[datetime],
    allowed_aisle_ids: Optional[set] = None,
) -> Optional[float]:
    """succeeded / (succeeded + failed) for aisle jobs with terminal outcome in period."""
    succeeded = 0
    failed = 0
    for j in jobs:
        if j.target_type != "aisle":
            continue
        if allowed_aisle_ids is not None and j.target_id not in allowed_aisle_ids:
            continue
        if not _ts_in_range(j.updated_at, date_from, date_to):
            continue
        if j.status == JobStatus.SUCCEEDED:
            succeeded += 1
        elif j.status == JobStatus.FAILED:
            failed += 1
        else:
            continue
    denom = succeeded + failed
    if denom == 0:
        return None
    return succeeded / denom


def issue_bucket_for_position(pos: Position) -> str:
    """Single primary bucket label for quality patterns (mutually exclusive priority)."""
    if is_invalid_traceability(pos):
        return "invalid_traceability"
    if not position_has_primary_evidence(pos):
        return "missing_evidence"
    _, qty = summary_sku_and_detected_quantity(pos)
    if qty == 0:
        return "quantity_zero"
    if is_low_confidence(pos):
        return "low_confidence"
    if pos.needs_review:
        return "pending_review"
    return "ok"


def most_common_issue_for_counts(counts: Dict[str, int]) -> Optional[str]:
    labels = {
        "invalid_traceability": "Invalid traceability",
        "missing_evidence": "Missing evidence",
        "quantity_zero": "Zero quantity",
        "low_confidence": "Low confidence",
        "pending_review": "Pending review",
    }
    skip = {"ok"}
    ranked = sorted(((k, v) for k, v in counts.items() if k not in skip and v > 0), key=lambda x: -x[1])
    if not ranked:
        return None
    return labels.get(ranked[0][0], ranked[0][0])
