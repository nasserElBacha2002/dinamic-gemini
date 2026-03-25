"""Schema compatibility state shared by startup, health, and readiness endpoints."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class SchemaGuardState:
    compatible: bool = True
    checked: bool = False
    required_version: Optional[str] = None
    current_version: Optional[str] = None
    service: Optional[str] = None
    reason: Optional[str] = None


schema_guard_state = SchemaGuardState()
