"""Phase 7 — per-asset processing observability API schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AvailableAssetActionsResponse(BaseModel):
    can_reprocess: bool
    can_retry_persistence: bool
    can_send_to_external: bool
    can_assign_manual: bool
    can_invalidate: bool
    can_view_sensitive_evidence: bool
    can_reconcile: bool = False


class MutationAssetResponse(BaseModel):
    asset_id: str
    state_version: int
    status: str | None = None
    command_id: str | None = None
    command_type: str | None = None
    idempotent_replay: bool = False


class AssetProcessingSummaryResponse(BaseModel):
    asset_id: str
    file_name: str | None = None
    thumbnail_url: str | None = None
    status: str
    requested_mode: str | None = None
    executed_strategy: str | None = None
    resolved_by: str | None = None
    internal_code: str | None = None
    quantity: float | None = None
    attempt_count: int = 0
    last_error_code: str | None = None
    warnings: list[str] = Field(default_factory=list)
    duration_ms: int | None = None
    persistence_status: str | None = None
    has_fallback: bool = False
    has_manual_result: bool = False
    estimated_external_cost: float | None = None
    state_version: int = 0


class ProcessingJobProgressSummaryResponse(BaseModel):
    total: int = 0
    resolved: int = 0
    failed: int = 0
    pending: int = 0
    processing: int = 0
    manual_review: int = 0
    unrecognized: int | None = 0
    cancelled: int | None = 0


class AssetProcessingListResponse(BaseModel):
    items: list[AssetProcessingSummaryResponse]
    total: int
    page: int
    page_size: int
    summary: ProcessingJobProgressSummaryResponse | None = None


class AssetProcessingDetailResponse(BaseModel):
    asset: AssetProcessingSummaryResponse
    current_state: dict[str, Any] = Field(default_factory=dict)
    active_result: dict[str, Any] | None = None
    position: dict[str, Any] | None = None
    attempts: list[dict[str, Any]] = Field(default_factory=list)
    external_requests: list[dict[str, Any]] = Field(default_factory=list)
    profile_snapshot: dict[str, Any] | None = None
    events: list[dict[str, Any]] = Field(default_factory=list)
    available_actions: AvailableAssetActionsResponse
    historical_incomplete: bool = False


class ProcessingEventRecordResponse(BaseModel):
    id: str
    event_type: str
    timestamp: str
    level: str | None = None
    message: str | None = None
    metadata: dict[str, Any] | None = None


class ProcessingEventsPageResponse(BaseModel):
    items: list[ProcessingEventRecordResponse]
    total: int
    page: int
    page_size: int
    has_more: bool = False


class ReprocessAssetRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)
    expected_state_version: int = Field(..., ge=0)
    strategy: str | None = None
    manual_policy: str | None = None


class InvalidateResultRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)
    expected_state_version: int = Field(..., ge=0)


class ProcessingObservabilityCapabilitiesResponse(BaseModel):
    processing_observability_enabled: bool
    processing_asset_logs_ui_enabled: bool = False
    processing_asset_reprocess_enabled: bool = False
    processing_manual_actions_enabled: bool = False
    processing_events_persistence_enabled: bool = False
