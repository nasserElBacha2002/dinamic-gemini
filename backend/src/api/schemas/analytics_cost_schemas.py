"""Pydantic schemas for analytics cost-summary (Phase 3)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AnalyticsCostSummaryScopeResponse(BaseModel):
    date_from: str | None = None
    date_to: str | None = None
    inventory_id: str | None = None
    aisle_id: str | None = None
    client_id: str | None = None
    client_supplier_id: str | None = None
    provider_name: str | None = None
    model_name: str | None = None


class AnalyticsCostTotalsResponse(BaseModel):
    jobs_total: int = 0
    jobs_with_cost: int = 0
    jobs_without_cost: int = 0
    jobs_with_exact_cost: int = 0
    jobs_with_estimated_cost: int = 0
    jobs_with_partial_cost: int = 0
    jobs_with_unavailable_cost: int = 0
    jobs_with_missing_cost: int = 0
    total_cost: float | None = None
    total_counted_quantity: int | None = None
    cost_per_counted_unit: float | None = None
    total_execution_time_seconds: float | None = None
    average_execution_time_seconds: float | None = None


class AnalyticsCostByProviderModelResponse(BaseModel):
    provider_name: str | None = None
    model_name: str | None = None
    jobs_total: int = 0
    jobs_with_cost: int = 0
    total_cost: float | None = None
    total_counted_quantity: int | None = None
    cost_per_counted_unit: float | None = None
    average_execution_time_seconds: float | None = None


class AnalyticsCostByInventoryResponse(BaseModel):
    inventory_id: str
    inventory_name: str | None = None
    jobs_total: int = 0
    jobs_with_cost: int = 0
    total_cost: float | None = None
    total_counted_quantity: int | None = None
    cost_per_counted_unit: float | None = None
    total_execution_time_seconds: float | None = None


class AnalyticsCostByAisleResponse(BaseModel):
    inventory_id: str
    inventory_name: str | None = None
    aisle_id: str
    aisle_code: str | None = None
    jobs_total: int = 0
    jobs_with_cost: int = 0
    total_cost: float | None = None
    total_counted_quantity: int | None = None
    cost_per_counted_unit: float | None = None
    total_execution_time_seconds: float | None = None


class AnalyticsCostByCaptureStatusResponse(BaseModel):
    capture_status: str
    jobs_total: int = 0
    total_cost: float | None = None


class AnalyticsCostSummaryResponse(BaseModel):
    """LLM processing cost aggregates for the unified analytics dashboard.

    Cost is job-grain (``finished_at`` in scope). Counted quantity is operational-grain
    (UI/export rollup) and may be null when scope cannot be resolved safely.
    """

    scope: AnalyticsCostSummaryScopeResponse
    totals: AnalyticsCostTotalsResponse
    by_provider_model: list[AnalyticsCostByProviderModelResponse] = Field(default_factory=list)
    by_inventory: list[AnalyticsCostByInventoryResponse] = Field(default_factory=list)
    by_aisle: list[AnalyticsCostByAisleResponse] = Field(default_factory=list)
    by_capture_status: list[AnalyticsCostByCaptureStatusResponse] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
