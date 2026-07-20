"""Durable mutation idempotency records (Phase 7 corrections)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class ProcessingActionIdempotencyRecord:
    id: str
    action_type: str
    job_id: str
    asset_id: str
    idempotency_key: str
    request_hash: str
    response_json: dict[str, Any]
    status: str
    created_at: datetime
    updated_at: datetime
    state_version: int | None = None
    actor: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


__all__ = ["ProcessingActionIdempotencyRecord"]
