"""Application-layer LLM cost snapshot shape (API-independent).

Used to validate persisted ``job.result_json["llm_cost_snapshot"]`` for read surfaces
without importing API schemas into the application layer.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


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
    price_units: str | None = None
    provider: str | None = None
    model: str | None = None
    canonical_model: str | None = None
    input_cost_per_million: str | None = None
    output_cost_per_million: str | None = None
    cached_input_cost_per_million: str | None = None
    thinking_cost_per_million: str | None = None
    cache_write_cost_per_million: str | None = None
    tool_request_unit_cost: str | None = None
    image_input_unit_cost: str | None = None
    audio_input_cost_per_million: str | None = None
    video_input_cost_per_million: str | None = None
    thinking_cost_rule: str | None = None
    thinking_billed_as: str | None = None
    pricing_confidence: str | None = None


class LlmComputedCostResponse(BaseModel):
    subtotal_input: str | None = None
    subtotal_output: str | None = None
    subtotal_cached: str | None = None
    subtotal_cache_write: str | None = None
    subtotal_thinking: str | None = None
    subtotal_tools: str | None = None
    subtotal_image: str | None = None
    subtotal_audio: str | None = None
    subtotal_video: str | None = None
    partial_total_cost: str | None = None
    total_cost: str | None = None
    currency: str | None = None
    total_cost_unavailable_reason: str | None = None


class LlmCostSnapshotResponse(BaseModel):
    provider: str
    model: str | None = None
    canonical_model: str | None = None
    pricing_available: bool | None = None
    billing_currency: str | None = None
    usage: LlmUsageSnapshotResponse
    pricing_snapshot: LlmPricingSnapshotResponse
    computed_cost: LlmComputedCostResponse
    capture_status: str
    capture_notes: list[str] = Field(default_factory=list)
