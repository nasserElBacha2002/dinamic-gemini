"""Phase 6/7 — benchmark compare / compare-many / promote payloads."""

from __future__ import annotations

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
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    cached_input_tokens: int | None = None
    cache_write_tokens: int | None = None
    thinking_tokens: int | None = None
    tool_requests: int | None = None
    image_input_count: int | None = None
    image_input_tokens: int | None = None
    audio_input_tokens: int | None = None
    video_input_tokens: int | None = None


class LlmPricingSnapshotResponse(BaseModel):
    pricing_source: str | None = None
    pricing_version: str | None = None
    captured_at: str | None = None
    pricing_catalog_entry_captured_at: str | None = None
    billing_currency: str | None = None
    input_cost_per_million: str | None = None
    output_cost_per_million: str | None = None
    cached_input_cost_per_million: str | None = None
    thinking_cost_per_million: str | None = None
    tool_request_unit_cost: str | None = None
    image_input_unit_cost: str | None = None
    audio_input_cost_per_million: str | None = None
    video_input_cost_per_million: str | None = None
    thinking_cost_rule: str | None = None


class LlmComputedCostResponse(BaseModel):
    subtotal_input: str | None = None
    subtotal_output: str | None = None
    subtotal_cached: str | None = None
    subtotal_thinking: str | None = None
    subtotal_tools: str | None = None
    subtotal_image: str | None = None
    subtotal_audio: str | None = None
    subtotal_video: str | None = None
    total_cost: str | None = None
    currency: str | None = None
    total_cost_unavailable_reason: str | None = None


class LlmCostSnapshotResponse(BaseModel):
    provider: str
    model: str | None = None
    pricing_available: bool | None = None
    billing_currency: str | None = None
    usage: LlmUsageSnapshotResponse
    pricing_snapshot: LlmPricingSnapshotResponse
    computed_cost: LlmComputedCostResponse
    capture_status: str
    capture_notes: list[str] = Field(default_factory=list)


class BenchmarkRunCompareSideResponse(BaseModel):
    job_id: str
    status: str
    provider_name: str | None = None
    model_name: str | None = None
    prompt_key: str | None = None
    prompt_version: str | None = None
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    #: Wall-clock duration ``finished_at - started_at`` when both are present and coherent.
    execution_time_seconds: float | None = None
    #: Same duration as compact text (e.g. ``12.4s``, ``1m 02s``); null when duration unknown.
    execution_time_human: str | None = None
    metrics: RunSliceMetricsResponse
    llm_cost_snapshot: LlmCostSnapshotResponse | None = None


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
    quantity_a: int | None = None
    quantity_b: int | None = None
    sku_a: str | None = None
    sku_b: str | None = None
    position_code_a: str | None = None
    position_code_b: str | None = None


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
    diff_rows: list[CompareDiffRowResponse]
    diff_rows_truncated: bool


class AisleBenchmarkCompareManyRequest(BaseModel):
    """Phase 1 compare-many payload (baseline-centric, constrained to 2-3 job ids)."""

    job_ids: list[str] = Field(..., min_length=2, max_length=3)
    baseline_job_id: str = Field(..., min_length=1)
    include_diff_rows: bool = Field(
        False,
        description="Phase 2: include lightweight baseline-vs-target diff rows.",
    )
    max_diff_rows: int | None = Field(
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
    #: ``target execution_time_seconds - baseline`` when both sides have a duration (seconds).
    execution_time_delta: float | None = None


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
    #: Min/max duration across selected jobs, only when **every** job has ``execution_time_seconds``.
    min_execution_time_seconds: float | None = None
    max_execution_time_seconds: float | None = None


class BenchmarkCompareManyDiffResponse(BaseModel):
    baseline_job_id: str
    target_job_id: str
    diff_summary: CompareDiffSummaryResponse
    delta: BenchmarkCompareManyDeltaResponse
    diff_rows: list[CompareDiffRowResponse] = Field(default_factory=list)
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
    jobs: list[BenchmarkCompareRunResponse]
    comparisons: list[BenchmarkCompareManyDiffResponse]
    summary: BenchmarkCompareManySummaryResponse
    raw_fetch_truncated: list[BenchmarkCompareManyRawFetchFlagResponse] = Field(
        default_factory=list
    )
