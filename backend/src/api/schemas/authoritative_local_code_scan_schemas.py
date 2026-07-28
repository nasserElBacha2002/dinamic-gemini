"""API schemas for authoritative local CODE_SCAN ingest."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AuthoritativeLocalCodeScanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(default="1", max_length=8)
    result_id: str = Field(..., min_length=1, max_length=36)
    client_file_id: str = Field(..., min_length=1, max_length=36)
    internal_code: str = Field(..., min_length=1, max_length=64)
    quantity: int | None = Field(default=None, ge=1, le=99_999_999)
    quantity_status: Literal["PRESENT", "MISSING"] = "PRESENT"
    source: Literal["LOCAL_CODE_SCAN", "LOCAL_MANUAL_CORRECTION"] = "LOCAL_CODE_SCAN"
    detected_internal_code: str | None = Field(default=None, max_length=64)
    detected_quantity: int | None = Field(default=None, ge=1, le=99_999_999)
    detected_symbology: str | None = Field(default=None, max_length=32)
    parser_version: str = Field(..., min_length=1, max_length=32)
    detector_version: str = Field(..., min_length=1, max_length=64)
    prepared_asset_sha256: str = Field(..., min_length=1, max_length=80)
    confirmed_by_user_id: str | None = Field(
        default=None,
        max_length=36,
        description="Ignored — confirmed_by is derived from authentication.",
    )
    confirmed_at: datetime | None = None


class AuthoritativeLocalCodeScanResponse(BaseModel):
    result_id: str
    asset_id: str
    result_version: int
    is_current: bool
    supersedes_result_id: str | None = None
    status: str
    duplicate: bool = False
    #: None until /process applies the final position (FINAL_POSITION_APPLIED).
    applied_at: datetime | None = None
