"""Phase 7 — operational processing events (structured timeline)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class ProcessingEvent:
    id: str
    job_id: str
    event_type: str
    created_at: datetime
    asset_id: str | None = None
    attempt_id: str | None = None
    strategy: str | None = None
    severity: str = "INFO"  # INFO | WARN | ERROR
    message: str | None = None
    error_code: str | None = None
    duration_ms: int | None = None
    correlation_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


__all__ = ["ProcessingEvent"]
