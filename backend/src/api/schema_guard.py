"""Schema compatibility state shared by startup, health, and readiness endpoints."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SchemaGuardState:
    compatible: bool = True
    checked: bool = False
    required_version: str | None = None
    current_version: str | None = None
    service: str | None = None
    reason: str | None = None


schema_guard_state = SchemaGuardState()
