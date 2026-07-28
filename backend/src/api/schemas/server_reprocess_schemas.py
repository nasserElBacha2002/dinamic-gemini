"""API schemas for Phase 7 server reprocess."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ServerReprocessScopeRequest(BaseModel):
    type: Literal[
        "FULL_AISLE",
        "SELECTED_ASSETS",
        "FAILED_ONLY",
        "UNRECOGNIZED_ONLY",
        "PENDING_REVIEW_ONLY",
    ]
    asset_ids: list[str] = Field(default_factory=list)


class ServerReprocessRequest(BaseModel):
    request_id: str = Field(min_length=1, max_length=64)
    scope: ServerReprocessScopeRequest
    processing_mode: Literal[
        "CODE_SCAN",
        "INTERNAL_OCR",
        "GLOBAL_FALLBACK",
        "AUTO_PIPELINE",
    ] = "CODE_SCAN"
    reason: str = "USER_REQUESTED_REPROCESS"
    source_session_id: str | None = None


class ServerReprocessRunResponse(BaseModel):
    id: str
    request_id: str
    inventory_id: str
    aisle_id: str
    run_type: str
    scope_type: str
    processing_mode: str
    reason: str
    status: str
    review_status: str
    has_prior_authority: bool
    requested_by: str
    requested_at: str
    started_at: str | None = None
    completed_at: str | None = None
    canceled_at: str | None = None
    failure_code: str | None = None
    failure_message: str | None = None
    row_version: int
    replayed: bool = False
    initial_server_processing: bool = False
    has_pending_server_reprocess: bool = True


class ServerReprocessProposalSummaryResponse(BaseModel):
    total: int
    same: int
    changed: int
    newly_resolved: int
    unresolved: int
    not_comparable: int = 0


class ServerReprocessProposalItemResponse(BaseModel):
    id: str
    run_id: str
    asset_id: str
    remote_result_id: str | None
    previous_result_id: str | None
    previous_position_id: str | None
    status: str
    difference_type: str
    internal_code: str | None
    quantity: float | None
    confidence: float | None
    source: str | None
    remote_resolved: bool
    review_status: str


class ServerReprocessDetailResponse(BaseModel):
    run: ServerReprocessRunResponse
    summary: ServerReprocessProposalSummaryResponse
    items: list[ServerReprocessProposalItemResponse]
    snapshot: dict[str, Any] = Field(default_factory=dict)


class ServerReprocessAdoptItemRequest(BaseModel):
    proposal_id: str
    action: Literal["ADOPT", "KEEP_CURRENT", "EDIT_AND_ADOPT", "DEFER"]
    edit_internal_code: str | None = None
    edit_quantity: float | None = None


class ServerReprocessAdoptRequest(BaseModel):
    adoption_id: str = Field(min_length=1, max_length=64)
    items: list[ServerReprocessAdoptItemRequest] = Field(min_length=1)


class ServerReprocessAdoptResponse(BaseModel):
    adoption_id: str
    run_id: str
    status: str
    review_status: str
    item_count: int
    adopted_count: int
    kept_count: int
    deferred_count: int
    replayed: bool = False


class ServerReprocessCompleteWithResultsItem(BaseModel):
    """Internal/test helper: attach remote outputs without persisting positions."""

    asset_id: str
    remote_result_id: str | None = None
    internal_code: str | None = None
    quantity: float | None = None
    confidence: float | None = None
    source: str | None = None
    resolved: bool = False
    ambiguous: bool = False
    comparable: bool = True
    global_batch_unmapped: bool = False


class ServerReprocessCompleteWithResultsRequest(BaseModel):
    results: list[ServerReprocessCompleteWithResultsItem] = Field(min_length=1)
