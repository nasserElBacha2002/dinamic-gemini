"""Durable per-asset processing commands (Phase 7 corrections)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class AssetProcessingCommandType(str, Enum):
    REPROCESS_FROM_SOURCE = "REPROCESS_FROM_SOURCE"
    RETRY_PERSISTENCE = "RETRY_PERSISTENCE"
    SEND_TO_EXTERNAL = "SEND_TO_EXTERNAL"
    RECONCILE_RESULT = "RECONCILE_RESULT"


class AssetProcessingCommandStatus(str, Enum):
    QUEUED = "QUEUED"
    CLAIMED = "CLAIMED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass
class AssetProcessingCommand:
    id: str
    job_id: str
    asset_id: str
    command_type: AssetProcessingCommandType
    status: AssetProcessingCommandStatus
    created_at: datetime
    requested_strategy: str | None = None
    idempotency_key: str | None = None
    expected_state_version: int | None = None
    actor: str | None = None
    reason: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    worker_token: str | None = None
    claimed_at: datetime | None = None
    completed_at: datetime | None = None
    error_code: str | None = None
    error_message: str | None = None


__all__ = [
    "AssetProcessingCommand",
    "AssetProcessingCommandStatus",
    "AssetProcessingCommandType",
]
