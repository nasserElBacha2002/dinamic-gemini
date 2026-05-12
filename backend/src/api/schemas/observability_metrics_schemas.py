"""Response schemas for GET /api/v3/observability/metrics (Phase H5)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ObservabilityMetricsRange(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    from_: str = Field(..., alias="from")
    to: str


class ObservabilityMetricsFiltersOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    client_id: str | None = None
    client_supplier_id: str | None = None
    provider_name: str | None = None
    model_name: str | None = None


class ObservabilityMetricsTotals(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    runs_total: int
    runs_succeeded: int
    runs_failed: int
    success_rate: float | None = None
    failure_rate: float | None = None
    fallback_runs: int
    missing_prompt_config_runs: int
    missing_reference_runs: int
    legacy_runs: int


class ObservabilityMetricsByClientRow(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    client_id: str | None = None
    runs_total: int
    runs_succeeded: int
    runs_failed: int
    failure_rate: float | None = None


class ObservabilityMetricsBySupplierRow(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    client_supplier_id: str | None = None
    client_id: str | None = None
    runs_total: int
    runs_succeeded: int
    runs_failed: int
    fallback_runs: int
    missing_reference_runs: int
    failure_rate: float | None = None


class ObservabilityMetricsByProviderModelRow(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    provider_name: str | None = None
    model_name: str | None = None
    runs_total: int
    runs_succeeded: int
    runs_failed: int
    failure_rate: float | None = None


class ObservabilityMetricsDataQuality(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    jobs_with_audit_snapshot: int
    jobs_without_audit_snapshot: int
    jobs_with_missing_metadata: int
    artifact_dependent_jobs: int


class ObservabilityMetricsResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    range_: ObservabilityMetricsRange = Field(..., alias="range")
    filters: ObservabilityMetricsFiltersOut
    totals: ObservabilityMetricsTotals
    by_client: list[ObservabilityMetricsByClientRow]
    by_supplier: list[ObservabilityMetricsBySupplierRow]
    by_provider_model: list[ObservabilityMetricsByProviderModelRow]
    data_quality: ObservabilityMetricsDataQuality
