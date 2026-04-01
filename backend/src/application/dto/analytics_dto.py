"""
Analytics DTOs — Phase 5.1 (v336).

Internal dataclasses for analytics service/repository. API layer maps these to Pydantic responses.

Metric definitions (abbreviated; see service helpers / docs for formulas):
- reviewed terminal actions: confirm, update_quantity, update_sku, mark_unknown (excludes delete_position).
- auto_acceptance_rate: confirmed terminal outcomes / reviewed positions.
- manual_correction_rate: (qty_corrected + sku_corrected) / reviewed positions.
- unknown_rate: unknown terminal outcomes / reviewed positions.
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
    auto_acceptance_rate: Optional[float]
    manual_correction_rate: Optional[float]
    # Transitional note: historical rows may still have ``review_resolution=None``.
    # Unknown metrics count only explicit persisted terminal unknown resolutions.
    unknown_rate: Optional[float]
    unknown_count: int
    invalid_traceability_rate: Optional[float]
    processing_success_rate: Optional[float]
    average_review_time_seconds: Optional[float]
    average_review_time_minutes: Optional[float]
    settling_actions_per_day: Optional[float]
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
    total_aisles: int
    aisles_count: int
    total_positions: int
    positions_count: int
    processed_positions: int
    processed_count: int
    review_rate: Optional[float]
    correction_rate: Optional[float]
    auto_acceptance_rate: Optional[float]
    manual_correction_rate: Optional[float]
    # Additive Phase 4 field. Null historical ``review_resolution`` values are excluded from
    # unknown counts rather than heuristically backfilled.
    unknown_rate: Optional[float]
    invalid_traceability_rate: Optional[float]
    avg_confidence: Optional[float]
    processing_success_rate: Optional[float]
    average_review_time_minutes: Optional[float]


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
    total_results: int
    needs_review_count: int
    corrected_count: int
    # Additive operational field for explicit persisted unknown terminal outcomes only.
    unknown_count: int
    # Narrow manual correction count: qty + SKU corrections only; excludes unknown/delete/invalid.
    manual_corrections_count: int
    invalid_traceability_count: int
    low_confidence_count: int
    most_common_issue: Optional[str]


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
