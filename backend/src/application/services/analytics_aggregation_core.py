"""
Pure helpers for analytics — shared by in-memory repository and tests.

LOW_CONFIDENCE_THRESHOLD matches review_queue_derived / frontend reviewThresholds.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence, Tuple

from src.application.constants.review_quality import LOW_CONFIDENCE_THRESHOLD
from src.application.dto.analytics_dto import AnalyticsFilters
from src.application.mappers.position_canonical_view import build_position_canonical_view
from src.application.utils.review_queue_derived import (
    position_has_primary_evidence,
    summary_sku_and_detected_quantity,
    traceability_normalized,
)
from src.domain.jobs.entities import Job, JobStatus
from src.domain.positions.entities import Position, PositionReviewResolution, PositionStatus
from src.domain.products.entities import ProductRecord
from src.domain.reviews.entities import ReviewAction, ReviewActionType


@dataclass(frozen=True)
class ReviewOutcomeCounts:
    reviewed_positions_count: int
    auto_accepted_positions_count: int
    manually_corrected_positions_count: int
    operator_marked_unknown_positions_count: int
    settling_actions_count: int


@dataclass(frozen=True)
class SummaryMetricInputs:
    total_positions_in_scope: int
    processed_positions_count: int
    reviewed_positions_count: int
    auto_accepted_positions_count: int
    manually_corrected_positions_count: int
    operator_marked_unknown_positions_count: int
    unidentified_product_positions_count: int
    invalid_traceability_positions_count: int
    processing_success_rate: Optional[float]
    average_review_time_seconds: Optional[float]
    settling_actions_per_day: Optional[float]
    settling_actions_count: int
    period_day_count: int
    notes: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class InventoryMetricInputs:
    total_positions_in_scope: int
    processed_positions_count: int
    reviewed_positions_count: int
    auto_accepted_positions_count: int
    manually_corrected_positions_count: int
    operator_marked_unknown_positions_count: int
    unidentified_product_positions_count: int
    invalid_traceability_positions_count: int
    avg_confidence: Optional[float]
    processing_success_rate: Optional[float]
    average_review_time_seconds: Optional[float]


@dataclass(frozen=True)
class ManualInterventionBreakdown:
    reviewed_positions_count: int
    intervention_positions_count: int
    confirmed_count: int
    qty_corrected_count: int
    sku_corrected_count: int
    operator_marked_unknown_count: int
    deleted_count: int
    unknown_available: bool
    invalid_available: bool
    notes: List[str] = field(default_factory=list)


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
    """Entity scope only (inventory/aisle). Date range does NOT gate position-state metrics."""
    if filters.inventory_id and inventory_id != filters.inventory_id:
        return False
    if filters.aisle_id and aisle_id != filters.aisle_id:
        return False
    return True


def active_position(pos: Position) -> bool:
    return pos.status != PositionStatus.DELETED


def is_invalid_traceability(pos: Position, primary_product: Optional[ProductRecord] = None) -> bool:
    view = build_position_canonical_view(pos, primary_product)
    status = (view.traceability.traceability_status or "").strip().lower()
    if status:
        return status == "invalid"
    return traceability_normalized(pos) == "invalid"


def is_low_confidence(pos: Position) -> bool:
    return pos.confidence < LOW_CONFIDENCE_THRESHOLD


def settling_action(ra: ReviewAction) -> bool:
    return ra.action_type in (
        ReviewActionType.CONFIRM,
        ReviewActionType.UPDATE_QUANTITY,
        ReviewActionType.UPDATE_SKU,
        ReviewActionType.MARK_UNKNOWN,
    )


def correction_action(ra: ReviewAction) -> bool:
    return ra.action_type in (ReviewActionType.UPDATE_QUANTITY, ReviewActionType.UPDATE_SKU)


def unknown_action(ra: ReviewAction) -> bool:
    return ra.action_type == ReviewActionType.MARK_UNKNOWN


def unidentified_product(primary_product: Optional[ProductRecord]) -> bool:
    if primary_product is None:
        return False
    return (primary_product.sku or "").strip().upper() == "UNKNOWN"


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


def processed_position(pos: Position) -> bool:
    return pos.status in (PositionStatus.REVIEWED, PositionStatus.CORRECTED) or (
        pos.status == PositionStatus.DETECTED and not pos.needs_review
    )


def compute_review_outcome_counts(
    actions: Sequence[ReviewAction],
    date_from: Optional[datetime],
    date_to: Optional[datetime],
) -> ReviewOutcomeCounts:
    """Unique reviewed-position counts plus backward-compatible settling action count.

    Review outcome semantics for Phase 2:
    - reviewed_positions_count: unique positions with at least one settling action in period
    - auto_accepted_positions_count: reviewed positions with confirm actions only
    - manually_corrected_positions_count: reviewed positions with any quantity/SKU correction

    This intentionally keeps ``manual_correction_rate`` narrow (quantity + SKU only).
    """
    latest_by_position: Dict[str, ReviewAction] = {}
    settling_actions_count = 0
    for ra in sorted(actions, key=lambda x: (x.created_at, x.id)):
        if not review_action_in_period(ra, date_from, date_to):
            continue
        if not settling_action(ra):
            continue
        settling_actions_count += 1
        latest_by_position[ra.position_id] = ra

    reviewed_positions_count = len(latest_by_position)
    auto_accepted_positions_count = 0
    manually_corrected_positions_count = 0
    operator_marked_unknown_positions_count = 0
    for ra in latest_by_position.values():
        if correction_action(ra):
            manually_corrected_positions_count += 1
        elif unknown_action(ra):
            operator_marked_unknown_positions_count += 1
        elif ra.action_type == ReviewActionType.CONFIRM:
            auto_accepted_positions_count += 1

    return ReviewOutcomeCounts(
        reviewed_positions_count=reviewed_positions_count,
        auto_accepted_positions_count=auto_accepted_positions_count,
        manually_corrected_positions_count=manually_corrected_positions_count,
        operator_marked_unknown_positions_count=operator_marked_unknown_positions_count,
        settling_actions_count=settling_actions_count,
    )


def ratio_or_none(numerator: int, denominator: int) -> Optional[float]:
    if denominator <= 0:
        return None
    return numerator / denominator


def minutes_from_seconds(seconds: Optional[float]) -> Optional[float]:
    if seconds is None:
        return None
    return seconds / 60.0


def build_summary_metrics(inputs: SummaryMetricInputs):
    from src.application.dto.analytics_dto import AnalyticsSummaryDTO

    return AnalyticsSummaryDTO(
        auto_acceptance_rate=ratio_or_none(
            inputs.auto_accepted_positions_count, inputs.reviewed_positions_count
        ),
        manual_correction_rate=ratio_or_none(
            inputs.manually_corrected_positions_count, inputs.reviewed_positions_count
        ),
        operator_marked_unknown_rate=ratio_or_none(
            inputs.operator_marked_unknown_positions_count, inputs.reviewed_positions_count
        ),
        operator_marked_unknown_count=inputs.operator_marked_unknown_positions_count,
        unidentified_product_rate=ratio_or_none(
            inputs.unidentified_product_positions_count, inputs.total_positions_in_scope
        ),
        unidentified_product_count=inputs.unidentified_product_positions_count,
        unknown_rate=ratio_or_none(
            inputs.operator_marked_unknown_positions_count, inputs.reviewed_positions_count
        ),
        unknown_count=inputs.operator_marked_unknown_positions_count,
        invalid_traceability_rate=ratio_or_none(
            inputs.invalid_traceability_positions_count, inputs.total_positions_in_scope
        ),
        processing_success_rate=inputs.processing_success_rate,
        average_review_time_seconds=inputs.average_review_time_seconds,
        average_review_time_minutes=minutes_from_seconds(inputs.average_review_time_seconds),
        settling_actions_per_day=inputs.settling_actions_per_day,
        notes=list(inputs.notes),
        period_day_count=inputs.period_day_count,
        settling_actions_count=inputs.settling_actions_count,
        positions_in_scope=inputs.total_positions_in_scope,
        total_positions_in_scope=inputs.total_positions_in_scope,
        processed_positions_count=inputs.processed_positions_count,
        reviewed_positions_count=inputs.reviewed_positions_count,
    )


def build_inventory_metric_rates(inputs: InventoryMetricInputs) -> dict:
    return {
        "review_rate": ratio_or_none(inputs.reviewed_positions_count, inputs.total_positions_in_scope),
        "correction_rate": ratio_or_none(
            inputs.manually_corrected_positions_count, inputs.reviewed_positions_count
        ),
        "auto_acceptance_rate": ratio_or_none(
            inputs.auto_accepted_positions_count, inputs.reviewed_positions_count
        ),
        "manual_correction_rate": ratio_or_none(
            inputs.manually_corrected_positions_count, inputs.reviewed_positions_count
        ),
        "operator_marked_unknown_rate": ratio_or_none(
            inputs.operator_marked_unknown_positions_count, inputs.reviewed_positions_count
        ),
        "unidentified_product_rate": ratio_or_none(
            inputs.unidentified_product_positions_count, inputs.total_positions_in_scope
        ),
        "unknown_rate": ratio_or_none(
            inputs.operator_marked_unknown_positions_count, inputs.reviewed_positions_count
        ),
        "invalid_traceability_rate": ratio_or_none(
            inputs.invalid_traceability_positions_count, inputs.total_positions_in_scope
        ),
        "avg_confidence": inputs.avg_confidence,
        "processing_success_rate": inputs.processing_success_rate,
        "average_review_time_minutes": minutes_from_seconds(inputs.average_review_time_seconds),
    }


def compute_manual_intervention_breakdown(
    actions: Sequence[ReviewAction],
    date_from: Optional[datetime],
    date_to: Optional[datetime],
) -> ManualInterventionBreakdown:
    """Mutually exclusive current persisted intervention categories by latest action in period.

    Unknown becomes available once persisted as a terminal review resolution. Invalid remains
    unavailable until modeled separately from delete_position.
    """
    latest_by_position: Dict[str, ReviewAction] = {}
    reviewed_positions: set[str] = set()
    intervention_positions: set[str] = set()
    for ra in sorted(actions, key=lambda x: (x.created_at, x.id)):
        if not review_action_in_period(ra, date_from, date_to):
            continue
        if ra.action_type in (
            ReviewActionType.CONFIRM,
            ReviewActionType.UPDATE_QUANTITY,
            ReviewActionType.UPDATE_SKU,
            ReviewActionType.MARK_UNKNOWN,
            ReviewActionType.DELETE_POSITION,
        ):
            intervention_positions.add(ra.position_id)
            latest_by_position[ra.position_id] = ra
        if settling_action(ra):
            reviewed_positions.add(ra.position_id)

    confirmed_count = 0
    qty_corrected_count = 0
    sku_corrected_count = 0
    operator_marked_unknown_count = 0
    deleted_count = 0
    for ra in latest_by_position.values():
        if ra.action_type == ReviewActionType.CONFIRM:
            confirmed_count += 1
        elif ra.action_type == ReviewActionType.UPDATE_QUANTITY:
            qty_corrected_count += 1
        elif ra.action_type == ReviewActionType.UPDATE_SKU:
            sku_corrected_count += 1
        elif ra.action_type == ReviewActionType.MARK_UNKNOWN:
            operator_marked_unknown_count += 1
        elif ra.action_type == ReviewActionType.DELETE_POSITION:
            deleted_count += 1

    return ManualInterventionBreakdown(
        reviewed_positions_count=len(reviewed_positions),
        intervention_positions_count=len(intervention_positions),
        confirmed_count=confirmed_count,
        qty_corrected_count=qty_corrected_count,
        sku_corrected_count=sku_corrected_count,
        operator_marked_unknown_count=operator_marked_unknown_count,
        deleted_count=deleted_count,
        unknown_available=True,
        invalid_available=False,
        notes=[
            "invalid category unavailable: current persisted review model does not distinguish invalid from delete_position",
        ],
    )


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


def issue_bucket_for_position(pos: Position, primary_product: Optional[ProductRecord] = None) -> str:
    """Single primary bucket label for quality patterns (mutually exclusive priority)."""
    if unidentified_product(primary_product):
        return "unidentified_product"
    if is_invalid_traceability(pos, primary_product):
        return "invalid_traceability"
    if not position_has_primary_evidence(pos):
        return "missing_evidence"
    view = build_position_canonical_view(pos, primary_product)
    qty = int(view.quantity.final_display_quantity)
    if primary_product is None and qty == 0:
        _, summary_qty = summary_sku_and_detected_quantity(pos)
        qty = summary_qty
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
        "unidentified_product": "Unidentified product",
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
