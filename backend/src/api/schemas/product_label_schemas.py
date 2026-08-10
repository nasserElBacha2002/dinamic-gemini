"""API schemas for physical product label minting (D1)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class IssueProductLabelsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    internal_code: str = Field(..., min_length=1, max_length=48)
    quantity: int = Field(..., ge=1, le=99_999_999)
    count: int = Field(1, ge=1, le=50)


class IssuedProductLabelResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label_id: str
    internal_code: str
    quantity: int
    format_version: str
    checksum: str
    payload: str
    created_at: datetime


class IssueProductLabelsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[IssuedProductLabelResponse]
