"""Pydantic schemas for /api/v3/analytics — Phase 5.1."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class AnalyticsSummaryResponse(BaseModel):
    auto_acceptance_rate: float | None = None
    manual_correction_rate: float | None = None
    operator_marked_unknown_rate: float | None = None
    operator_marked_unknown_count: int = 0
    unidentified_product_rate: float | None = None
    unidentified_product_count: int = 0
    unknown_rate: float | None = None
    unknown_count: int = 0
    invalid_traceability_rate: float | None = None
    processing_success_rate: float | None = None
    average_processing_time_seconds: float | None = None
    average_processing_time_minutes: float | None = None
    settling_actions_per_day: float | None = None
    notes: list[str] = Field(default_factory=list)
    period_day_count: int = 0
    settling_actions_count: int = 0
    positions_in_scope: int = 0
    total_positions_in_scope: int = 0
    processed_positions_count: int = 0
    reviewed_positions_count: int = 0


class TrendPointResponse(BaseModel):
    period: str
    reviewed_results: int = 0
    correction_rate: float | None = None
    processing_success_rate: float | None = None


class AnalyticsTrendsResponse(BaseModel):
    reviewed_results_over_time: list[TrendPointResponse] = Field(default_factory=list)
    correction_rate_over_time: list[TrendPointResponse] = Field(default_factory=list)
    processing_success_over_time: list[TrendPointResponse] = Field(default_factory=list)


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
    review_rate: float | None = None
    correction_rate: float | None = None
    auto_acceptance_rate: float | None = None
    manual_correction_rate: float | None = None
    operator_marked_unknown_rate: float | None = None
    unidentified_product_rate: float | None = None
    unknown_rate: float | None = None
    invalid_traceability_rate: float | None = None
    avg_confidence: float | None = None
    processing_success_rate: float | None = None
    average_processing_time_minutes: float | None = None


class InventoryPerformanceListResponse(BaseModel):
    items: list[InventoryPerformanceRowResponse] = Field(default_factory=list)


class AisleIssueRowResponse(BaseModel):
    aisle_id: str
    aisle_code: str
    inventory_id: str
    inventory_name: str
    total_results: int
    needs_review_count: int
    corrected_count: int
    operator_marked_unknown_count: int
    unidentified_product_count: int
    unknown_count: int
    manual_corrections_count: int
    invalid_traceability_count: int
    low_confidence_count: int
    most_common_issue: str | None = None


class AisleIssueListResponse(BaseModel):
    items: list[AisleIssueRowResponse] = Field(default_factory=list)


class QualityPatternRowResponse(BaseModel):
    issue_type: str
    count: int
    percentage: float | None = None
    notes: str | None = None


class QualityPatternListResponse(BaseModel):
    items: list[QualityPatternRowResponse] = Field(default_factory=list)


class ManualInterventionCategoryResponse(BaseModel):
    category: str
    count: int | None = None
    percentage: float | None = None
    available: bool = True
    notes: str | None = None


class ManualInterventionBreakdownResponse(BaseModel):
    reviewed_positions_count: int = 0
    intervention_positions_count: int = 0
    items: list[ManualInterventionCategoryResponse] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
