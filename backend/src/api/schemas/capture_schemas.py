"""v3 capture session API schemas — Sprint 2."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from src.api.schemas.listing_schemas import PageMeta
from src.domain.capture.entities import CaptureSession, CaptureSessionItem


class CaptureSessionResponse(BaseModel):
    id: str
    inventory_id: str
    aisle_id: str
    status: str
    created_at: datetime
    updated_at: datetime
    opened_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None


class CaptureSessionItemResponse(BaseModel):
    id: str
    session_id: str
    staging_storage_key: str
    import_status: str
    assignment_status: str
    content_hash: Optional[str] = None
    linked_source_asset_id: Optional[str] = None
    last_error_code: Optional[str] = None
    last_error_detail: Optional[str] = None
    original_filename: Optional[str] = None
    updated_at: datetime


class CaptureSessionDetailResponse(BaseModel):
    session: CaptureSessionResponse
    items: List[CaptureSessionItemResponse]


class PaginatedCaptureSessionListResponse(PageMeta):
    items: List[CaptureSessionResponse]


class UploadCaptureSessionItemsResponse(BaseModel):
    items: List[CaptureSessionItemResponse] = Field(default_factory=list)


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
    )


def capture_session_item_to_response(i: CaptureSessionItem) -> CaptureSessionItemResponse:
    return CaptureSessionItemResponse(
        id=i.id,
        session_id=i.session_id,
        staging_storage_key=i.staging_storage_key,
        import_status=i.import_status.value,
        assignment_status=i.assignment_status.value,
        content_hash=i.content_hash,
        linked_source_asset_id=i.linked_source_asset_id,
        last_error_code=i.last_error_code,
        last_error_detail=i.last_error_detail,
        original_filename=i.original_filename,
        updated_at=i.updated_at,
    )
