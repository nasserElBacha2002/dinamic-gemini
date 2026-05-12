"""Client domain entity — Phase A1 foundation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class ClientStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"


@dataclass
class Client:
    id: str
    name: str
    status: ClientStatus
    created_at: datetime
    updated_at: datetime

