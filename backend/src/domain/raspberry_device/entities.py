"""Client-scoped Raspberry device credentials."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class RaspberryDeviceStatus(str, Enum):
    ACTIVE = "ACTIVE"
    REVOKED = "REVOKED"


@dataclass(frozen=True)
class RaspberryDevice:
    id: str
    client_id: str
    name: str
    token_hash: str
    status: RaspberryDeviceStatus
    created_at: datetime
    last_used_at: datetime | None = None