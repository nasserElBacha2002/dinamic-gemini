"""Client domain entity — Phase A1 foundation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from src.domain.aisle_identification.modes import AisleIdentificationMode


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
    #: Optional default aisle identification mode; null inherits system default (LEGACY_LLM).
    default_identification_mode: AisleIdentificationMode | None = None

