"""API schemas for mobile preliminary detection sync (Phase 4)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PositionSignatureEvidenceV2(BaseModel):
    model_config = ConfigDict(extra="forbid")

    present: bool
    verification: Literal["MISSING", "UNVERIFIED", "INVALID", "NOT_APPLICABLE"]


class PositionReferenceV2(BaseModel):
    """Untrusted mobile position evidence; server validation remains authoritative."""

    model_config = ConfigDict(extra="forbid")

    payload_version: Literal[2]
    local_recognition_id: str = Field(..., min_length=1, max_length=128)
    raw_code: str = Field(..., min_length=1, max_length=4000)
    normalized_code: str = Field(..., min_length=1, max_length=64)
    remote_position_id: str | None = Field(default=None, max_length=36)
    remote_position_label_id: str | None = Field(default=None, max_length=36)
    source: Literal[
        "LOCAL_CODE_SCAN",
        "SERVER_CODE_SCAN",
        "VISION",
        "OCR",
        "TXT",
        "MANUAL",
    ]
    profile_id: str | None = Field(default=None, max_length=36)
    profile_version: int | None = Field(default=None, ge=1)
    client_supplier_id: str | None = Field(default=None, max_length=36)
    signature: PositionSignatureEvidenceV2
    captured_at: datetime


class PositionAuthoritativeResultV2(BaseModel):
    contract_version: Literal[2] = 2
    local_recognition_id: str
    normalized_code: str | None
    remote_position_id: str | None
    remote_position_label_id: str | None
    status: Literal[
        "ACCEPTED_EXISTING",
        "ACCEPTED_UNMATERIALIZED",
        "REJECTED_FORMAT",
        "REJECTED_PROFILE",
        "REJECTED_SCOPE",
        "REJECTED_INVENTORY_STATE",
        "REJECTED_AMBIGUOUS",
        "REJECTED_DUPLICATE",
        "RETRYABLE_ERROR",
    ]
    error_code: str | None
    retryable: bool
    server_timestamp: datetime
    reconciliation_revision: int = Field(default=0, ge=0)


class PreliminaryDetectionUpsertRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1", "2"] = "1"
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
    position_reference: PositionReferenceV2 | None = None

    @model_validator(mode="after")
    def validate_versioned_position_reference(self) -> PreliminaryDetectionUpsertRequest:
        if self.schema_version == "2" and self.position_reference is None:
            raise ValueError("position_reference is required for schema_version 2")
        if self.schema_version == "1" and self.position_reference is not None:
            raise ValueError("position_reference requires schema_version 2")
        return self


class PreliminaryDetectionUpsertResponse(BaseModel):
    draft_id: str
    requested_draft_id: str
    server_preliminary_id: str
    status: str
    received_at: datetime
    validation_errors: list[str] = Field(default_factory=list)
    duplicate: bool = False
    position_result: PositionAuthoritativeResultV2 | None = None
