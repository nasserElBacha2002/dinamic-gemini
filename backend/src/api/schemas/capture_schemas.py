"""v3 capture session API schemas — Sprint 2."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional, Sequence

from pydantic import BaseModel, Field

from src.api.schemas.listing_schemas import PageMeta
from src.application.ports.capture_repositories import CaptureSessionGroupSummary
from src.domain.capture.entities import CaptureSession, CaptureSessionItem


class CaptureSessionResponse(BaseModel):
    id: str
    inventory_id: str
    aisle_id: Optional[str] = None
    status: str
    created_at: datetime
    updated_at: datetime
    opened_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    clock_offset_seconds: int = 0


class CaptureSessionItemResponse(BaseModel):
    id: str
    session_id: str
    staging_storage_key: str
    import_status: str
    assignment_status: str
    content_hash: Optional[str] = None
    effective_capture_time: Optional[datetime] = None
    time_source: Optional[str] = None
    time_confidence: Optional[float] = None
    adjusted_capture_time: Optional[datetime] = None
    assignment_reason: Optional[str] = None
    preview_target_position_id: Optional[str] = None
    linked_source_asset_id: Optional[str] = None
    last_error_code: Optional[str] = None
    last_error_detail: Optional[str] = None
    original_filename: Optional[str] = None
    group_id: Optional[str] = None
    updated_at: datetime


class CaptureSessionGroupSummaryResponse(BaseModel):
    group_id: str
    group_index: int
    item_count: int
    start_time: datetime
    end_time: datetime


class CaptureSessionGroupsListResponse(BaseModel):
    groups: List[CaptureSessionGroupSummaryResponse] = Field(default_factory=list)


def capture_session_groups_to_response(summaries: Sequence[CaptureSessionGroupSummary]) -> CaptureSessionGroupsListResponse:
    return CaptureSessionGroupsListResponse(
        groups=[
            CaptureSessionGroupSummaryResponse(
                group_id=s.group_id,
                group_index=s.group_index,
                item_count=s.item_count,
                start_time=s.start_time,
                end_time=s.end_time,
            )
            for s in summaries
        ]
    )


class CaptureSessionDetailResponse(BaseModel):
    session: CaptureSessionResponse
    items: List[CaptureSessionItemResponse]


class PaginatedCaptureSessionListResponse(PageMeta):
    items: List[CaptureSessionResponse]


class CaptureSessionStagingUploadFileError(BaseModel):
    filename: str
    code: str
    detail: str
    file_index: int = Field(ge=0, description="Index into the multipart files list for this request.")


class UploadCaptureSessionItemsResponse(BaseModel):
    items: List[CaptureSessionItemResponse] = Field(default_factory=list)
    errors: List[CaptureSessionStagingUploadFileError] = Field(default_factory=list)


class CaptureSessionClockOffsetUpdateRequest(BaseModel):
    """Sprint 3 — session-level offset applied at preview (``effective`` + offset → ``adjusted``)."""

    clock_offset_seconds: int


class CaptureSessionMaterializeRequest(BaseModel):
    idempotency_key: str = Field(min_length=1, max_length=255)


class MaterializeCaptureSessionResponse(CaptureSessionDetailResponse):
    created_assets_count: int = 0


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
