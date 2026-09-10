"""Read scoped position-flexible rollout capabilities (Phase 5)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Protocol


class PositionFlexibleCapabilityMode(str, Enum):
    SHADOW = "SHADOW"
    ENFORCED = "ENFORCED"


@dataclass(frozen=True)
class PositionFlexibleCapability:
    id: str
    client_id: str
    channel: str
    mode: PositionFlexibleCapabilityMode
    enabled: bool
    client_supplier_id: str | None = None
    profile_id: str | None = None
    reason: str | None = None
    created_by: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class PositionFlexibleCapabilityReader(Protocol):
    def find_enabled(
        self,
        *,
        client_id: str,
        channel: str,
        client_supplier_id: str | None = None,
        profile_id: str | None = None,
    ) -> PositionFlexibleCapability | None:
        """Return the most specific enabled capability for the scope, or None."""
        ...
