"""API schemas for aisle revisions (Phase 8)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


RevisionTypeLiteral = Literal[
    "MANUAL_CORRECTION",
    "SERVER_PROPOSAL_ADOPTION",
    "ROLLBACK",
    "EXCLUSION_CHANGE",
    "REOPEN_AND_EDIT",
]


class CreateAisleRevisionRequest(BaseModel):
    revision_id: str = Field(..., min_length=1, max_length=36)
    revision_type: RevisionTypeLiteral = "MANUAL_CORRECTION"
    reason: str = Field(..., min_length=1, max_length=500)


class UpdateAisleRevisionItemRequest(BaseModel):
    internal_code: str | None = Field(default=None, max_length=128)
    quantity: int | None = None
    exclusion_action: Literal["EXCLUDE", "RESTORE"] | None = None
    reason: str | None = Field(default=None, max_length=500)
    proposal_source: str | None = None
    proposal_reference_id: str | None = None


class ApplyAisleRevisionRequest(BaseModel):
    apply_id: str = Field(..., min_length=1, max_length=64)
    expected_base_finalization_id: str = Field(..., min_length=1, max_length=36)


class RollbackAisleRequest(BaseModel):
    rollback_id: str = Field(..., min_length=1, max_length=36)
    target_finalization_id: str = Field(..., min_length=1, max_length=36)
    reason: str = Field(..., min_length=1, max_length=500)
    apply_immediately: bool = True


class AisleRevisionItemResponse(BaseModel):
    id: str
    asset_id: str
    base_result_id: str | None = None
    base_position_id: str | None = None
    proposed_internal_code: str | None = None
    proposed_quantity: int | None = None
    proposed_exclusion_state: str | None = None
    proposal_source: str
    proposal_reference_id: str | None = None
    change_reason: str | None = None
    item_status: str


class AisleRevisionResponse(BaseModel):
    id: str
    inventory_id: str
    aisle_id: str
    base_finalization_id: str
    new_finalization_id: str | None = None
    revision_type: str
    status: str
    reason: str
    requested_by: str
    requested_at: str
    completed_at: str | None = None
    apply_id: str | None = None
    content_hash: str
    row_version: int
    replayed: bool = False
    items: list[AisleRevisionItemResponse] = Field(default_factory=list)


class AisleRevisionDiffEntryResponse(BaseModel):
    asset_id: str
    kind: str
    base_internal_code: str | None = None
    proposed_internal_code: str | None = None
    base_quantity: int | None = None
    proposed_quantity: int | None = None
    item_status: str
    proposal_source: str


class AisleRevisionDiffResponse(BaseModel):
    revision_id: str
    entries: list[AisleRevisionDiffEntryResponse]


class AisleHistoryEntryResponse(BaseModel):
    revision_id: str
    revision_type: str
    status: str
    reason: str
    requested_by: str
    requested_at: str
    completed_at: str | None = None
    base_finalization_id: str
    new_finalization_id: str | None = None
    changed_asset_count: int
    total_assets: int


class AisleRevisionCapabilitiesResponse(BaseModel):
    aisle_revisions_enabled: bool
    aisle_rollback_enabled: bool
    aisle_history_enabled: bool
