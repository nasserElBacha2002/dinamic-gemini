"""API schemas for mobile preliminary detection sync (Phase 4)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PreliminaryDetectionUpsertRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(default="1", max_length=8)
    capture_session_id: str | None = Field(default=None, max_length=36)
    capture_photo_id: str | None = Field(default=None, max_length=36)
    client_file_id: str = Field(..., min_length=1, max_length=36)
    asset_id: str = Field(..., min_length=1, max_length=36)
    processing_mode: Literal["CODE_SCAN"] = "CODE_SCAN"
    status: str = Field(..., min_length=1, max_length=32)
    internal_code: str | None = Field(default=None, max_length=64)
    quantity: int | None = Field(default=None, ge=1, le=99_999_999)
    quantity_status: str | None = Field(default=None, max_length=16)
    detected_format: str | None = Field(default=None, max_length=32)
    detected_symbology: str | None = Field(default=None, max_length=32)
    candidate_count: int = Field(default=0, ge=0, le=100)
    parser_version: str = Field(..., min_length=1, max_length=32)
    detector_version: str = Field(..., min_length=1, max_length=64)
    prepared_asset_sha256: str = Field(..., min_length=1, max_length=80)
    payload_hash: str | None = Field(default=None, max_length=80)
    processing_ms: int | None = Field(default=None, ge=0, le=600_000)
    detected_at: datetime | None = None


class PreliminaryDetectionUpsertResponse(BaseModel):
    draft_id: str
    requested_draft_id: str
    server_preliminary_id: str
    status: str
    received_at: datetime
    validation_errors: list[str] = Field(default_factory=list)
    duplicate: bool = False
