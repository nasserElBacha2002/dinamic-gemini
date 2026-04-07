"""Phase 6 — benchmark compare / promote payloads (explicit, read-only compare)."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class PromoteOperationalJobRequest(BaseModel):
    job_id: str = Field(..., min_length=1, description="Succeeded process_aisle job id to promote.")


class PromoteOperationalJobResponse(BaseModel):
    aisle_id: str
    operational_job_id: str


class RunSliceMetricsResponse(BaseModel):
    raw_rows_considered: int
    consolidated_positions: int
    total_quantity: int
    unknown_internal_code_count: int
    needs_review_count: int


class BenchmarkRunCompareSideResponse(BaseModel):
    job_id: str
    status: str
    provider_name: Optional[str] = None
    model_name: Optional[str] = None
    prompt_key: Optional[str] = None
    prompt_version: Optional[str] = None
    created_at: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    metrics: RunSliceMetricsResponse


class CompareDiffSummaryResponse(BaseModel):
    keys_only_in_a: int
    keys_only_in_b: int
    keys_in_both: int
    quantity_changed: int
    sku_changed: int
    position_code_changed: int


class CompareDiffRowResponse(BaseModel):
    match_key: str
    side: str
    quantity_a: Optional[int] = None
    quantity_b: Optional[int] = None
    sku_a: Optional[str] = None
    sku_b: Optional[str] = None
    position_code_a: Optional[str] = None
    position_code_b: Optional[str] = None


class RawFetchTruncatedFlags(BaseModel):
    job_a: bool
    job_b: bool


class AisleBenchmarkCompareResponse(BaseModel):
    """Structured compare payload for two explicit runs of the same aisle."""

    inventory_id: str
    aisle_id: str
    workflow: str
    read_only: bool
    raw_fetch_truncated: RawFetchTruncatedFlags
    run_a: BenchmarkRunCompareSideResponse
    run_b: BenchmarkRunCompareSideResponse
    diff_summary: CompareDiffSummaryResponse
    diff_rows: List[CompareDiffRowResponse]
    diff_rows_truncated: bool
