"""API schemas for authoritative aisle finalization (Phase 6)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AuthoritativeAisleReadinessResponse(BaseModel):
    status: str
    total_images: int
    applied_images: int
    excluded_images: int
    pending_images: int
    conflicted_images: int
    failed_images: int
    reasons: list[str] = Field(default_factory=list)
    unique_codes: int = 0
    total_quantity: int = 0


class FinalizeAuthoritativeAisleRequest(BaseModel):
    finalization_id: str = Field(..., min_length=1, max_length=36)
    expected_asset_count: int = Field(..., ge=0)
    client_session_id: str | None = Field(default=None, max_length=36)


class FinalizeAuthoritativeAisleResponse(BaseModel):
    finalization_id: str
    status: str
    aisle_status: str
    total_assets: int
    applied_assets: int
    excluded_assets: int
    position_count: int
    idempotent_replay: bool = False
