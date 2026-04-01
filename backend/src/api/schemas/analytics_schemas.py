"""Pydantic schemas for /api/v3/analytics — Phase 5.1."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class AnalyticsSummaryResponse(BaseModel):
    auto_acceptance_rate: Optional[float] = None
    manual_correction_rate: Optional[float] = None
    invalid_traceability_rate: Optional[float] = None
    processing_success_rate: Optional[float] = None
    average_review_time_seconds: Optional[float] = None
    average_review_time_minutes: Optional[float] = None
    settling_actions_per_day: Optional[float] = None
    notes: List[str] = Field(default_factory=list)
    period_day_count: int = 0
    settling_actions_count: int = 0
    positions_in_scope: int = 0
    total_positions_in_scope: int = 0
    processed_positions_count: int = 0
    reviewed_positions_count: int = 0


class TrendPointResponse(BaseModel):
    period: str
    reviewed_results: int = 0
    correction_rate: Optional[float] = None
    processing_success_rate: Optional[float] = None


class AnalyticsTrendsResponse(BaseModel):
    reviewed_results_over_time: List[TrendPointResponse] = Field(default_factory=list)
    correction_rate_over_time: List[TrendPointResponse] = Field(default_factory=list)
    processing_success_over_time: List[TrendPointResponse] = Field(default_factory=list)


class InventoryPerformanceRowResponse(BaseModel):
    inventory_id: str
    inventory_name: str
    inventory_created_at: datetime
    total_aisles: int
    aisles_count: int
    total_positions: int
    positions_count: int
    processed_positions: int
    processed_count: int
    review_rate: Optional[float] = None
    correction_rate: Optional[float] = None
    auto_acceptance_rate: Optional[float] = None
    manual_correction_rate: Optional[float] = None
    invalid_traceability_rate: Optional[float] = None
    avg_confidence: Optional[float] = None
    processing_success_rate: Optional[float] = None
    average_review_time_minutes: Optional[float] = None


class InventoryPerformanceListResponse(BaseModel):
    items: List[InventoryPerformanceRowResponse] = Field(default_factory=list)


class AisleIssueRowResponse(BaseModel):
    aisle_id: str
    aisle_code: str
    inventory_id: str
    inventory_name: str
    total_results: int
    needs_review_count: int
    corrected_count: int
    invalid_traceability_count: int
    low_confidence_count: int
    most_common_issue: Optional[str] = None


class AisleIssueListResponse(BaseModel):
    items: List[AisleIssueRowResponse] = Field(default_factory=list)


class QualityPatternRowResponse(BaseModel):
    issue_type: str
    count: int
    percentage: Optional[float] = None
    notes: Optional[str] = None


class QualityPatternListResponse(BaseModel):
    items: List[QualityPatternRowResponse] = Field(default_factory=list)


class ManualInterventionCategoryResponse(BaseModel):
    category: str
    count: Optional[int] = None
    percentage: Optional[float] = None
    available: bool = True
    notes: Optional[str] = None


class ManualInterventionBreakdownResponse(BaseModel):
    reviewed_positions_count: int = 0
    intervention_positions_count: int = 0
    items: List[ManualInterventionCategoryResponse] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)
