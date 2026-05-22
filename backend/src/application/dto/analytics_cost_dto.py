"""DTOs for analytics cost-summary aggregates (Phase 3)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True)
class AnalyticsCostSummaryFilters:
    """Scope for global dashboard LLM cost aggregates (job-grain)."""

    finished_from: datetime
    finished_to: datetime
    inventory_id: str | None = None
    aisle_id: str | None = None
    client_id: str | None = None
    client_supplier_id: str | None = None
    provider_name: str | None = None
    model_name: str | None = None


@dataclass(frozen=True)
class AnalyticsCostSummaryScopeDTO:
    date_from: str | None
    date_to: str | None
    inventory_id: str | None
    aisle_id: str | None
    client_id: str | None
    client_supplier_id: str | None
    provider_name: str | None
    model_name: str | None


@dataclass
class AnalyticsCostTotalsDTO:
    jobs_total: int = 0
    jobs_with_cost: int = 0
    jobs_without_cost: int = 0
    jobs_with_exact_cost: int = 0
    jobs_with_estimated_cost: int = 0
    jobs_with_partial_cost: int = 0
    jobs_with_unavailable_cost: int = 0
    jobs_with_missing_cost: int = 0
    total_cost: Decimal | None = None
    total_counted_quantity: int | None = None
    cost_per_counted_unit: Decimal | None = None
    total_execution_time_seconds: float | None = None
    average_execution_time_seconds: float | None = None


@dataclass
class AnalyticsCostByProviderModelDTO:
    provider_name: str | None
    model_name: str | None
    jobs_total: int = 0
    jobs_with_cost: int = 0
    total_cost: Decimal | None = None
    total_counted_quantity: int | None = None
    cost_per_counted_unit: Decimal | None = None
    average_execution_time_seconds: float | None = None


@dataclass
class AnalyticsCostByInventoryDTO:
    inventory_id: str
    inventory_name: str | None
    jobs_total: int = 0
    jobs_with_cost: int = 0
    total_cost: Decimal | None = None
    total_counted_quantity: int | None = None
    cost_per_counted_unit: Decimal | None = None
    total_execution_time_seconds: float | None = None


@dataclass
class AnalyticsCostByAisleDTO:
    inventory_id: str
    inventory_name: str | None
    aisle_id: str
    aisle_code: str | None
    jobs_total: int = 0
    jobs_with_cost: int = 0
    total_cost: Decimal | None = None
    total_counted_quantity: int | None = None
    cost_per_counted_unit: Decimal | None = None
    total_execution_time_seconds: float | None = None


@dataclass
class AnalyticsCostByCaptureStatusDTO:
    capture_status: str
    jobs_total: int = 0
    total_cost: Decimal | None = None


@dataclass
class AnalyticsCostSummaryDTO:
    scope: AnalyticsCostSummaryScopeDTO
    totals: AnalyticsCostTotalsDTO
    by_provider_model: list[AnalyticsCostByProviderModelDTO] = field(default_factory=list)
    by_inventory: list[AnalyticsCostByInventoryDTO] = field(default_factory=list)
    by_aisle: list[AnalyticsCostByAisleDTO] = field(default_factory=list)
    by_capture_status: list[AnalyticsCostByCaptureStatusDTO] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
