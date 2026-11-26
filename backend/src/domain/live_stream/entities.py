"""Live stream persistence entities — DIN-508 Phase 3."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class LiveChannelCredentials:
    id: str
    inventory_id: str
    canonical_aisle_code: str
    channel_slug: str
    mediamtx_path: str
    publish_username: str
    publish_password_hash: str
    read_username: str
    read_password_hash: str
    created_by_principal_id: str
    created_at: datetime
    updated_at: datetime
    publish_blocked_at: datetime | None = None
    publish_blocked_by_principal_id: str | None = None

    @property
    def publish_blocked(self) -> bool:
        return self.publish_blocked_at is not None


@dataclass(frozen=True)
class LiveViewGrant:
    id: str
    inventory_id: str
    channel_slug: str
    mediamtx_path: str
    token_hash: str
    view_username: str
    view_password_hash: str
    created_by_principal_id: str
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None
