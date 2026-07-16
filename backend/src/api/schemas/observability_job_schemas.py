"""Observability job-scoped API contracts (artifacts, retry chain, paged log, timeline, errors)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class CursorPageMeta(BaseModel):
    next_cursor: str | None = None
    has_more: bool = False


class JobArtifactSourceResponse(BaseModel):
    type: str
    source_asset_id: str | None = None


class JobArtifactResponse(BaseModel):
    id: str
    job_id: str
    category: str
    kind: str
    stage: str | None = None
    display_name: str
    original_filename: str | None = None
    mime_type: str | None = None
    size_bytes: int | None = None
    checksum: str | None = None
    width: int | None = None
    height: int | None = None
    status: str
    is_current: bool
    is_previewable: bool
    is_downloadable: bool
    created_at: datetime | None = None
    published_at: datetime | None = None
    expires_at: datetime | None = None
    source: JobArtifactSourceResponse


class JobArtifactPageResponse(BaseModel):
    items: list[JobArtifactResponse]
    page: CursorPageMeta
    inputs_legacy_unverified: bool = False


class RetryChainAttemptResponse(BaseModel):
    job_id: str
    attempt_number: int
    status: str
    started_at: datetime | None = None
    finished_at: datetime | None = None
    failure_code: str | None = None
    failure_message: str | None = None
    execution_id: str | None = None
    provider_name: str | None = None
    model_name: str | None = None
    is_selected: bool
    is_current: bool
    is_successful: bool


class JobRetryChainResponse(BaseModel):
    root_job_id: str
    selected_job_id: str
    current_job_id: str
    integrity: str = "VALID"
    warnings: list[str] = Field(default_factory=list)
    attempts: list[RetryChainAttemptResponse]


class ExecutionLogFiltersMeta(BaseModel):
    available_levels: list[str] = Field(default_factory=list)
    available_stages: list[str] = Field(default_factory=list)
    available_event_types: list[str] = Field(default_factory=list)


class ExecutionLogPageResponse(BaseModel):
    inventory_id: str
    aisle_id: str
    requested_job_id: str
    items: list[dict[str, Any]]
    page: CursorPageMeta
    filters: ExecutionLogFiltersMeta
    pagination_mode: str = "incremental"
    truncated: bool = False
    bytes_scanned: int | None = None


class JobTimelineEventResponse(BaseModel):
    id: str
    job_id: str
    execution_id: str | None = None
    event_type: str
    stage: str | None = None
    level: str = "info"
    timestamp: str | None = None
    sequence: int
    previous_status: str | None = None
    new_status: str | None = None
    message: str | None = None
    duration_ms: int | None = None
    provider: str | None = None
    provider_request_id: str | None = None
    error_code: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class JobTimelinePageResponse(BaseModel):
    items: list[JobTimelineEventResponse]
    page: CursorPageMeta


class JobErrorResponse(BaseModel):
    error_id: str
    job_id: str
    stage: str | None = None
    error_category: str | None = None
    error_code: str | None = None
    provider: str | None = None
    provider_code: str | None = None
    provider_request_id: str | None = None
    http_status: int | None = None
    message: str | None = None
    sanitized_detail: str | None = None
    retryable: bool | None = None
    attempt_number: int | None = None
    occurred_at: str | None = None
    stack_trace_available: bool = False


class JobErrorPageResponse(BaseModel):
    items: list[JobErrorResponse]
    page: CursorPageMeta


class ArtifactPreviewResponse(BaseModel):
    artifact_id: str
    kind: str
    mime_type: str | None = None
    truncated: bool = False
    preview_kind: Literal["text", "json", "metadata"] = "metadata"
    content: str | None = None
    size_bytes: int | None = None
    status: str
