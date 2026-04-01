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
- average_review_time_seconds: mean(first settling action time - position.created_at) for positions with such action in period.
- settling_actions_per_day: COUNT(settling review actions in period) / day span (min 1 day). Not unique positions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, List, Optional


@dataclass(frozen=True)
class AnalyticsFilters:
    """UTC date range optional; inventory/aisle narrow the scope."""

    date_from: Optional[datetime] = None  # inclusive
    date_to: Optional[datetime] = None  # inclusive (end of day should be set by caller)
    inventory_id: Optional[str] = None
    aisle_id: Optional[str] = None


@dataclass
class AnalyticsSummaryDTO:
    auto_acceptance_rate: Optional[float] = None
    manual_correction_rate: Optional[float] = None
    # Explicit review-flow unknown outcome: persisted terminal operator action only.
    operator_marked_unknown_rate: Optional[float] = None
    operator_marked_unknown_count: int = 0
    # Product-identification issue: display-primary product row has ``sku='UNKNOWN'``.
    unidentified_product_rate: Optional[float] = None
    unidentified_product_count: int = 0
    # Deprecated compatibility alias for the former overloaded ``unknown`` name.
    unknown_rate: Optional[float] = None
    unknown_count: int = 0
    invalid_traceability_rate: Optional[float] = None
    processing_success_rate: Optional[float] = None
    average_review_time_seconds: Optional[float] = None
    average_review_time_minutes: Optional[float] = None
    settling_actions_per_day: Optional[float] = None
    notes: List[str] = field(default_factory=list)
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
    correction_rate: Optional[float]
    processing_success_rate: Optional[float]


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
    review_rate: Optional[float] = None
    correction_rate: Optional[float] = None
    auto_acceptance_rate: Optional[float] = None
    manual_correction_rate: Optional[float] = None
    operator_marked_unknown_rate: Optional[float] = None
    unidentified_product_rate: Optional[float] = None
    # Deprecated compatibility alias for the former overloaded ``unknown`` name.
    unknown_rate: Optional[float] = None
    invalid_traceability_rate: Optional[float] = None
    avg_confidence: Optional[float] = None
    processing_success_rate: Optional[float] = None
    average_review_time_minutes: Optional[float] = None


@dataclass
class ManualInterventionCategoryDTO:
    category: str
    count: Optional[int]
    percentage: Optional[float]
    available: bool = True
    notes: Optional[str] = None


@dataclass
class ManualInterventionBreakdownDTO:
    reviewed_positions_count: int
    intervention_positions_count: int
    items: List[ManualInterventionCategoryDTO] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


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
    most_common_issue: Optional[str] = None


@dataclass
class QualityPatternRowDTO:
    issue_type: str
    count: int
    percentage: Optional[float]
    notes: Optional[str] = None


@dataclass
class AnalyticsTrendsDTO:
    reviewed_results_over_time: List[TrendPointDTO] = field(default_factory=list)
    correction_rate_over_time: List[TrendPointDTO] = field(default_factory=list)
    processing_success_over_time: List[TrendPointDTO] = field(default_factory=list)
