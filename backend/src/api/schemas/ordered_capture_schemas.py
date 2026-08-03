"""v3 ordered capture session API schemas (Phase 1 positioning foundation)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from src.domain.ordered_capture.entities import OrderedCaptureSession


class SealOrderedCaptureSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_asset_count: int = Field(..., ge=0)
    sequence_version: int = Field(..., ge=1)


class OrderedCaptureSessionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    inventory_id: str
    aisle_id: str
    status: str
    created_at: datetime
    updated_at: datetime
    client_id: str | None = None
    expected_asset_count: int | None = None
    uploaded_asset_count: int = 0
    sequence_version: int = 1
    created_by: str | None = None
    sealed_at: datetime | None = None
    processing_started_at: datetime | None = None
    completed_at: datetime | None = None


def ordered_capture_session_to_response(
    session: OrderedCaptureSession,
) -> OrderedCaptureSessionResponse:
    return OrderedCaptureSessionResponse(
        id=session.id,
        inventory_id=session.inventory_id,
        aisle_id=session.aisle_id,
        status=session.status.value,
        created_at=session.created_at,
        updated_at=session.updated_at,
        client_id=session.client_id,
        expected_asset_count=session.expected_asset_count,
        uploaded_asset_count=session.uploaded_asset_count,
        sequence_version=session.sequence_version,
        created_by=session.created_by,
        sealed_at=session.sealed_at,
        processing_started_at=session.processing_started_at,
        completed_at=session.completed_at,
    )
