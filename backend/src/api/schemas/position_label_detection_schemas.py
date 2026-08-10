"""API schemas for image position label detections (Phase 3)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from src.domain.position_label_detection.entities import ImagePositionLabelDetection


class PositionLabelSummaryDto(BaseModel):
    id: str | None = None
    name: str | None = None
    public_identifier: str | None = None


class ImagePositionDetectionDto(BaseModel):
    id: str
    asset_id: str
    sequence_number: int | None = None
    status: str
    signature_status: str
    payload_version: int | None = None
    position_label: PositionLabelSummaryDto | None = None
    confidence: float | None = None
    detector_version: str
    created_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class ImagePositionDetectionListResponse(BaseModel):
    items: list[ImagePositionDetectionDto]


def detection_to_dto(row: ImagePositionLabelDetection) -> ImagePositionDetectionDto:
    label = None
    if row.position_label_id or row.position_name_snapshot or row.public_identifier:
        # CLIENT_MISMATCH intentionally omits label details.
        if row.detection_status.value != "CLIENT_MISMATCH":
            label = PositionLabelSummaryDto(
                id=row.position_label_id,
                name=row.position_name_snapshot,
                public_identifier=row.public_identifier,
            )
    return ImagePositionDetectionDto(
        id=row.id,
        asset_id=row.source_asset_id,
        sequence_number=row.sequence_number,
        status=row.detection_status.value,
        signature_status=row.signature_status.value,
        payload_version=row.payload_version,
        position_label=label,
        confidence=row.confidence,
        detector_version=row.detector_version,
        created_at=row.created_at,
        metadata=dict(row.metadata_json or {}),
    )
