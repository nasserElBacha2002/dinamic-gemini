"""
Analytics DTOs — Phase 5.1 (v336).

Internal dataclasses for analytics service/repository. API layer maps these to Pydantic responses.

Metric definitions (abbreviated; see service docstrings for formulas):
- Settling review actions: confirm, update_quantity, update_sku (excludes delete_position).
- auto_acceptance_rate: confirm / settling actions in period.
- manual_correction_rate: (update_quantity + update_sku) / settling actions in period.
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
    invalid_traceability_rate: Optional[float]
    processing_success_rate: Optional[float]
    average_review_time_seconds: Optional[float]
    settling_actions_per_day: Optional[float]
    notes: List[str] = field(default_factory=list)
    period_day_count: int = 0
    settling_actions_count: int = 0
    positions_in_scope: int = 0


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
    total_positions: int
    processed_positions: int
    review_rate: Optional[float]
    correction_rate: Optional[float]
    invalid_traceability_rate: Optional[float]
    avg_confidence: Optional[float]
    processing_success_rate: Optional[float]


@dataclass
class AisleIssueRowDTO:
    aisle_id: str
    aisle_code: str
    inventory_id: str
    inventory_name: str
    total_results: int
    needs_review_count: int
    corrected_count: int
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
