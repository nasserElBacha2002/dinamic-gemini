"""Live stream API schemas — DIN-508 Phase 3."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class LiveStreamPrepareRequest(BaseModel):
    aisle_code: str = Field(min_length=1, max_length=64)


class LiveStreamStatusResponse(BaseModel):
    presence: str
    publisher_ready: bool
    bytes_received: int | None = None
    publish_blocked: bool = False


class LiveStreamStopRequest(BaseModel):
    aisle_code: str = Field(min_length=1, max_length=64)


class LiveStreamStopResponse(BaseModel):
    aisle_code: str
    canonical_aisle_code: str
    mediamtx_path: str
    publisher_kicked: bool
    status: LiveStreamStatusResponse


class LiveStreamPrepareResponse(BaseModel):
    inventory_id: str
    aisle_code: str
    canonical_aisle_code: str
    channel_slug: str
    mediamtx_path: str
    aisle_id: str | None
    rtmp_publish_url: str
    publish_username: str
    publish_password: str
    read_username: str
    read_password: str
    hls_playlist_url: str
    status: LiveStreamStatusResponse


class LiveStreamPlaybackResponse(BaseModel):
    mediamtx_path: str
    hls_playlist_url: str
    read_username: str
    read_password: str
    status: LiveStreamStatusResponse


class CreatePublicLiveGrantRequest(BaseModel):
    aisle_code: str = Field(min_length=1, max_length=64)
    ttl_hours: int | None = Field(default=None, ge=1, le=24 * 30)


class PublicLiveGrantResponse(BaseModel):
    grant_id: str
    public_url: str
    expires_at: datetime
    view_username: str
    view_password: str


class PublicLiveGrantListItem(BaseModel):
    grant_id: str
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None


class PublicLivePlaybackResponse(BaseModel):
    presence: str
    hls_playlist_url: str
    view_username: str
    view_password: str
    expires_at: datetime
    publish_blocked: bool = False
