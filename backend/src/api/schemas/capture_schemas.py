"""v3 capture session API schemas — Sprint 2."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from src.api.schemas.listing_schemas import PageMeta
from src.application.ports.capture_repositories import CaptureSessionGroupSummary
from src.application.use_cases.capture_sessions.compute_materialized_capture_session_group_preview import (
    ComputeMaterializedCaptureSessionGroupPreviewResult,
)
from src.domain.capture.entities import CaptureSession, CaptureSessionItem


class CaptureSessionResponse(BaseModel):
    id: str
    inventory_id: str
    aisle_id: str | None = None
    status: str
    created_at: datetime
    updated_at: datetime
    opened_at: datetime | None = None
    closed_at: datetime | None = None
    clock_offset_seconds: int = 0


class CaptureSessionItemResponse(BaseModel):
    id: str
    session_id: str
    staging_storage_key: str
    import_status: str
    assignment_status: str
    content_hash: str | None = None
    effective_capture_time: datetime | None = None
    time_source: str | None = None
    time_confidence: float | None = None
    adjusted_capture_time: datetime | None = None
    assignment_reason: str | None = None
    preview_target_position_id: str | None = None
    linked_source_asset_id: str | None = None
    last_error_code: str | None = None
    last_error_detail: str | None = None
    original_filename: str | None = None
    group_id: str | None = None
    updated_at: datetime


class CaptureSessionGroupSummaryResponse(BaseModel):
    group_id: str
    group_index: int
    item_count: int
    start_time: datetime
    end_time: datetime
    algorithm_version: str
    assignment_status: str = "unassigned"
    assigned_aisle_id: str | None = None
    assigned_at: datetime | None = None
    #: G7 derived: ``unassigned`` | ``assigned`` | ``materialized`` | ``partially_materialized``.
    materialization_state: str = "unassigned"


class CaptureSessionGroupsListResponse(BaseModel):
    groups: list[CaptureSessionGroupSummaryResponse] = Field(default_factory=list)


def capture_session_groups_to_response(
    summaries: Sequence[CaptureSessionGroupSummary],
) -> CaptureSessionGroupsListResponse:
    return CaptureSessionGroupsListResponse(
        groups=[
            CaptureSessionGroupSummaryResponse(
                group_id=s.group_id,
                group_index=s.group_index,
                item_count=s.item_count,
                start_time=s.start_time,
                end_time=s.end_time,
                algorithm_version=s.algorithm_version,
                assignment_status=s.assignment_status,
                assigned_aisle_id=s.assigned_aisle_id,
                assigned_at=s.assigned_at,
                materialization_state=s.materialization_state,
            )
            for s in summaries
        ]
    )


class AssignCaptureSessionGroupToExistingAisleRequest(BaseModel):
    """G4 — POST .../groups/{group_id}/assign-existing body."""

    aisle_id: str = Field(..., min_length=1, max_length=64)


class CreateAisleFromCaptureGroupRequest(BaseModel):
    """G4 — POST .../groups/{group_id}/create-aisle body (same ``code`` semantics as POST /aisles)."""

    code: str = Field(..., min_length=1, max_length=64)
    client_supplier_id: str | None = Field(
        None,
        description=(
            "Supplier for the new aisle. Required when the inventory has a client (validated server-side)."
        ),
    )

    @field_validator("client_supplier_id")
    @classmethod
    def validate_client_supplier_id_not_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("client_supplier_id must not be empty")
        return normalized


class CaptureSessionDetailResponse(BaseModel):
    session: CaptureSessionResponse
    items: list[CaptureSessionItemResponse]


class PaginatedCaptureSessionListResponse(PageMeta):
    items: list[CaptureSessionResponse]


class CaptureSessionStagingUploadFileError(BaseModel):
    filename: str
    code: str
    detail: str
    file_index: int = Field(
        ge=0, description="Index into the multipart files list for this request."
    )
    client_file_id: str | None = None


class UploadCaptureSessionItemsResponse(BaseModel):
    items: list[CaptureSessionItemResponse] = Field(default_factory=list)
    errors: list[CaptureSessionStagingUploadFileError] = Field(default_factory=list)


class CaptureSessionClockOffsetUpdateRequest(BaseModel):
    """Sprint 3 — session-level offset applied at preview (``effective`` + offset → ``adjusted``)."""

    clock_offset_seconds: int


class CaptureSessionMaterializeRequest(BaseModel):
    idempotency_key: str = Field(min_length=1, max_length=255)


class MaterializeCaptureSessionResponse(CaptureSessionDetailResponse):
    created_assets_count: int = 0


class MaterializeCaptureSessionGroupResponse(BaseModel):
    """G5 — materialize one assigned temporal group into ``SourceAsset`` rows on the group's aisle."""

    group_id: str
    aisle_id: str
    created_assets: int
    skipped_assets: int
    failed_assets: int = 0
    status: str = "materialized"


class MaterializeAllCaptureSessionGroupsResponse(BaseModel):
    """G5 — materialize every assigned group for a session (unassigned groups are skipped)."""

    total_groups: int
    materialized_groups: int
    skipped_groups: int
    total_assets_created: int
    total_assets_skipped: int
    total_assets_failed: int = 0


class MaterializedGroupPreviewItemResponse(BaseModel):
    """G6 — one materialized asset row joined to its capture item preview outcome."""

    capture_session_item_id: str
    source_asset_id: str
    assignment_status: str
    assignment_reason: str
    adjusted_capture_time: datetime | None = None
    preview_target_position_id: str | None = None


class MaterializedGroupPreviewSummaryResponse(BaseModel):
    proposed_count: int
    conflict_count: int
    unassigned_count: int
    previewed_item_count: int


class MaterializedCaptureSessionGroupPreviewResponse(BaseModel):
    """G6 — downstream preview over ``SourceAsset`` rows for one assigned temporal group."""

    capture_session_id: str
    group_id: str
    aisle_id: str
    source_asset_count: int
    source_asset_ids: list[str] = Field(default_factory=list)
    preview_status: str
    #: G7 operator-facing state for HTTP 200 responses (mirrors ``preview_status``).
    preview_operator_state: str
    items: list[MaterializedGroupPreviewItemResponse] = Field(default_factory=list)
    summary: MaterializedGroupPreviewSummaryResponse


def materialized_capture_session_group_preview_to_response(
    result: ComputeMaterializedCaptureSessionGroupPreviewResult,
) -> MaterializedCaptureSessionGroupPreviewResponse:
    return MaterializedCaptureSessionGroupPreviewResponse(
        capture_session_id=result.capture_session_id,
        group_id=result.group_id,
        aisle_id=result.aisle_id,
        source_asset_count=result.source_asset_count,
        source_asset_ids=list(result.source_asset_ids),
        preview_status=result.preview_status,
        preview_operator_state=result.preview_operator_state,
        items=[
            MaterializedGroupPreviewItemResponse(
                capture_session_item_id=i.capture_session_item_id,
                source_asset_id=i.source_asset_id,
                assignment_status=i.assignment_status,
                assignment_reason=i.assignment_reason,
                adjusted_capture_time=i.adjusted_capture_time,
                preview_target_position_id=i.preview_target_position_id,
            )
            for i in result.items
        ],
        summary=MaterializedGroupPreviewSummaryResponse(
            proposed_count=result.summary.proposed_count,
            conflict_count=result.summary.conflict_count,
            unassigned_count=result.summary.unassigned_count,
            previewed_item_count=result.summary.previewed_item_count,
        ),
    )


def capture_session_to_response(s: CaptureSession) -> CaptureSessionResponse:
    return CaptureSessionResponse(
        id=s.id,
        inventory_id=s.inventory_id,
        aisle_id=s.aisle_id,
        status=s.status.value,
        created_at=s.created_at,
        updated_at=s.updated_at,
        opened_at=s.opened_at,
        closed_at=s.closed_at,
        clock_offset_seconds=int(s.clock_offset_seconds),
    )


def capture_session_item_to_response(i: CaptureSessionItem) -> CaptureSessionItemResponse:
    return CaptureSessionItemResponse(
        id=i.id,
        session_id=i.session_id,
        staging_storage_key=i.staging_storage_key,
        import_status=i.import_status.value,
        assignment_status=i.assignment_status.value,
        content_hash=i.content_hash,
        effective_capture_time=i.effective_capture_time,
        time_source=i.time_source.value if i.time_source else None,
        time_confidence=i.time_confidence,
        adjusted_capture_time=i.adjusted_capture_time,
        assignment_reason=i.assignment_reason,
        preview_target_position_id=i.preview_target_position_id,
        linked_source_asset_id=i.linked_source_asset_id,
        last_error_code=i.last_error_code,
        last_error_detail=i.last_error_detail,
        original_filename=i.original_filename,
        group_id=i.group_id,
        updated_at=i.updated_at,
    )
