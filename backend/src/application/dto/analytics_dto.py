"""
Analytics DTOs — Phase 5.1 (v336).

Internal dataclasses for analytics service/repository. API layer maps these to Pydantic responses.

 Metric definitions (abbreviated; see service helpers / docs for formulas):
- reviewed terminal actions: confirm, update_quantity, update_sku, mark_unknown (excludes delete_position).
- auto_acceptance_rate: confirmed terminal outcomes / reviewed positions.
- manual_correction_rate: (qty_corrected + sku_corrected) / reviewed positions.
- operator_marked_unknown_rate: operator-marked unknown terminal outcomes / reviewed positions.
- unidentified_product_rate: positions whose display-primary product SKU is ``UNKNOWN`` / total positions in scope.
- invalid_traceability_rate: positions with detected_summary traceability_status='invalid' / non-deleted positions in scope.
- processing_success_rate: aisle jobs with status succeeded / (succeeded + failed), updated in period.
- average_processing_time_seconds: mean(finished_at - started_at) for terminal aisle jobs (succeeded, failed,
  canceled) with both timestamps, filtered by job finished_at in period.
- settling_actions_per_day: COUNT(settling review actions in period) / day span (min 1 day). Not unique positions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class AnalyticsFilters:
    """UTC date range optional; inventory/aisle narrow the scope."""

    date_from: datetime | None = None  # inclusive
    date_to: datetime | None = None  # inclusive (end of day should be set by caller)
    inventory_id: str | None = None
    aisle_id: str | None = None


@dataclass
class AnalyticsSummaryDTO:
    auto_acceptance_rate: float | None = None
    manual_correction_rate: float | None = None
    # Explicit review-flow unknown outcome: persisted terminal operator action only.
    operator_marked_unknown_rate: float | None = None
    operator_marked_unknown_count: int = 0
    # Product-identification issue: display-primary product row has ``sku='UNKNOWN'``.
    unidentified_product_rate: float | None = None
    unidentified_product_count: int = 0
    # Deprecated compatibility alias for the former overloaded ``unknown`` name.
    unknown_rate: float | None = None
    unknown_count: int = 0
    invalid_traceability_rate: float | None = None
    processing_success_rate: float | None = None
    average_processing_time_seconds: float | None = None
    average_processing_time_minutes: float | None = None
    settling_actions_per_day: float | None = None
    notes: list[str] = field(default_factory=list)
    period_day_count: int = 0
    settling_actions_count: int = 0
    positions_in_scope: int = 0
    total_positions_in_scope: int = 0
    processed_positions_count: int = 0
    reviewed_positions_count: int = 0


@dataclass
class TrendPointDTO:
    period: str  # ISO date YYYY-MM-DD
    reviewed_results: int
    correction_rate: float | None
    processing_success_rate: float | None


@dataclass
class InventoryPerformanceRowDTO:
    inventory_id: str
    inventory_name: str
    inventory_created_at: datetime
    total_aisles: int = 0
    aisles_count: int = 0
    total_positions: int = 0
    positions_count: int = 0
    processed_positions: int = 0
    processed_count: int = 0
    review_rate: float | None = None
    correction_rate: float | None = None
    auto_acceptance_rate: float | None = None
    manual_correction_rate: float | None = None
    operator_marked_unknown_rate: float | None = None
    unidentified_product_rate: float | None = None
    # Deprecated compatibility alias for the former overloaded ``unknown`` name.
    unknown_rate: float | None = None
    invalid_traceability_rate: float | None = None
    avg_confidence: float | None = None
    processing_success_rate: float | None = None
    average_processing_time_minutes: float | None = None


@dataclass
class ManualInterventionCategoryDTO:
    category: str
    count: int | None
    percentage: float | None
    available: bool = True
    notes: str | None = None


@dataclass
class ManualInterventionBreakdownDTO:
    reviewed_positions_count: int
    intervention_positions_count: int
    items: list[ManualInterventionCategoryDTO] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class AisleIssueRowDTO:
    aisle_id: str
    aisle_code: str
    inventory_id: str
    inventory_name: str
    total_results: int = 0
    needs_review_count: int = 0
    corrected_count: int = 0
    # Explicit persisted operator-marked unknown terminal outcomes only.
    operator_marked_unknown_count: int = 0
    # Product-identification issue: display-primary product row has ``sku='UNKNOWN'``.
    unidentified_product_count: int = 0
    # Deprecated compatibility alias for the former overloaded ``unknown`` name.
    unknown_count: int = 0
    # Narrow manual correction count: qty + SKU corrections only; excludes unknown/delete/invalid.
    manual_corrections_count: int = 0
    invalid_traceability_count: int = 0
    low_confidence_count: int = 0
    most_common_issue: str | None = None


@dataclass
class QualityPatternRowDTO:
    issue_type: str
    count: int
    percentage: float | None
    notes: str | None = None


@dataclass
class AnalyticsTrendsDTO:
    reviewed_results_over_time: list[TrendPointDTO] = field(default_factory=list)
    correction_rate_over_time: list[TrendPointDTO] = field(default_factory=list)
    processing_success_over_time: list[TrendPointDTO] = field(default_factory=list)
