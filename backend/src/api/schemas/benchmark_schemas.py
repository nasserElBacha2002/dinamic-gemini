"""Phase 6/7 — benchmark compare / compare-many / promote payloads."""

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


class LlmUsageSnapshotResponse(BaseModel):
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    cached_input_tokens: Optional[int] = None
    cache_write_tokens: Optional[int] = None
    thinking_tokens: Optional[int] = None
    tool_requests: Optional[int] = None
    image_input_count: Optional[int] = None
    image_input_tokens: Optional[int] = None
    audio_input_tokens: Optional[int] = None
    video_input_tokens: Optional[int] = None


class LlmPricingSnapshotResponse(BaseModel):
    pricing_source: Optional[str] = None
    pricing_version: Optional[str] = None
    captured_at: Optional[str] = None
    pricing_catalog_entry_captured_at: Optional[str] = None
    billing_currency: Optional[str] = None
    input_cost_per_million: Optional[str] = None
    output_cost_per_million: Optional[str] = None
    cached_input_cost_per_million: Optional[str] = None
    thinking_cost_per_million: Optional[str] = None
    tool_request_unit_cost: Optional[str] = None
    image_input_unit_cost: Optional[str] = None
    audio_input_cost_per_million: Optional[str] = None
    video_input_cost_per_million: Optional[str] = None
    thinking_cost_rule: Optional[str] = None


class LlmComputedCostResponse(BaseModel):
    subtotal_input: Optional[str] = None
    subtotal_output: Optional[str] = None
    subtotal_cached: Optional[str] = None
    subtotal_thinking: Optional[str] = None
    subtotal_tools: Optional[str] = None
    subtotal_image: Optional[str] = None
    subtotal_audio: Optional[str] = None
    subtotal_video: Optional[str] = None
    total_cost: Optional[str] = None
    currency: Optional[str] = None
    total_cost_unavailable_reason: Optional[str] = None


class LlmCostSnapshotResponse(BaseModel):
    provider: str
    model: Optional[str] = None
    pricing_available: Optional[bool] = None
    billing_currency: Optional[str] = None
    usage: LlmUsageSnapshotResponse
    pricing_snapshot: LlmPricingSnapshotResponse
    computed_cost: LlmComputedCostResponse
    capture_status: str
    capture_notes: List[str] = Field(default_factory=list)


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
    llm_cost_snapshot: Optional[LlmCostSnapshotResponse] = None


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
    """Per-run signal when the raw row fetch count reached the configured cap (not proof of extra rows)."""

    job_a: bool = Field(
        ...,
        description="Run A: raw load hit V3 cap — compare for this side may be incomplete.",
    )
    job_b: bool = Field(
        ...,
        description="Run B: raw load hit V3 cap — compare for this side may be incomplete.",
    )


class AisleBenchmarkCompareResponse(BaseModel):
    """Structured compare payload for two explicit runs of the same aisle."""

    inventory_id: str
    aisle_id: str
    workflow: str
    read_only: bool
    raw_fetch_truncated: RawFetchTruncatedFlags = Field(
        ...,
        description=(
            "When true, that run's raw fetch count reached the configured cap; totals may be incomplete. "
            "This does not assert that more rows exist beyond the cap."
        ),
    )
    run_a: BenchmarkRunCompareSideResponse
    run_b: BenchmarkRunCompareSideResponse
    diff_summary: CompareDiffSummaryResponse
    diff_rows: List[CompareDiffRowResponse]
    diff_rows_truncated: bool


class AisleBenchmarkCompareManyRequest(BaseModel):
    """Phase 1 compare-many payload (baseline-centric, constrained to 2-3 job ids)."""

    job_ids: List[str] = Field(..., min_length=2, max_length=3)
    baseline_job_id: str = Field(..., min_length=1)
    include_diff_rows: bool = Field(
        False,
        description="Phase 2: include lightweight baseline-vs-target diff rows.",
    )
    max_diff_rows: Optional[int] = Field(
        None,
        ge=1,
        le=250,
        description="Optional per-comparison cap when include_diff_rows=true.",
    )


class BenchmarkCompareRunResponse(BenchmarkRunCompareSideResponse):
    """Neutral run model for compare-many (kept separate from A/B side naming)."""


class BenchmarkCompareManyDeltaResponse(BaseModel):
    total_quantity_diff: int
    consolidated_positions_diff: int
    unknown_internal_code_diff: int
    needs_review_diff: int


class BenchmarkCompareManySummaryResponse(BaseModel):
    job_count: int
    baseline_job_id: str
    max_total_quantity: int
    min_total_quantity: int
    max_needs_review: int
    min_needs_review: int
    max_consolidated_positions: int
    min_consolidated_positions: int
    max_unknown_internal_code_count: int
    min_unknown_internal_code_count: int


class BenchmarkCompareManyDiffResponse(BaseModel):
    baseline_job_id: str
    target_job_id: str
    diff_summary: CompareDiffSummaryResponse
    delta: BenchmarkCompareManyDeltaResponse
    diff_rows: List[CompareDiffRowResponse] = Field(default_factory=list)
    diff_rows_truncated: bool = False


class BenchmarkCompareManyRawFetchFlagResponse(BaseModel):
    job_id: str
    truncated: bool = Field(
        ...,
        description=(
            "True when this run's raw fetch count reached the configured cap; "
            "totals may be incomplete."
        ),
    )


class AisleBenchmarkCompareManyResponse(BaseModel):
    inventory_id: str
    aisle_id: str
    workflow: str
    read_only: bool
    baseline_job_id: str
    jobs: List[BenchmarkCompareRunResponse]
    comparisons: List[BenchmarkCompareManyDiffResponse]
    summary: BenchmarkCompareManySummaryResponse
    raw_fetch_truncated: List[BenchmarkCompareManyRawFetchFlagResponse] = Field(default_factory=list)
