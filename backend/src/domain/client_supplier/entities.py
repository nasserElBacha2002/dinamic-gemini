"""Client supplier domain entity — Phase A2 foundation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class ClientSupplierStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"


@dataclass
class ClientSupplier:
    id: str
    client_id: str
    name: str
    status: ClientSupplierStatus
    created_at: datetime
    updated_at: datetime

