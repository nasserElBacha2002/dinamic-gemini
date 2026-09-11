"""Immutable contracts for canonical physical-position materialization."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

MAX_ID_LENGTH = 36
MAX_ACTOR_LENGTH = 128
MAX_IDEMPOTENCY_KEY_LENGTH = 128
MAX_NORMALIZED_CODE_LENGTH = 64
MAX_RAW_CODE_LENGTH = 4000


class PositionMaterializationStatus(str, Enum):
    MATERIALIZED = "MATERIALIZED"
    REUSED = "REUSED"
    REJECTED_VALIDATION = "REJECTED_VALIDATION"
    REJECTED_SCOPE = "REJECTED_SCOPE"
    REJECTED_IDEMPOTENCY_CONFLICT = "REJECTED_IDEMPOTENCY_CONFLICT"
    REJECTED_IDENTITY_CONFLICT = "REJECTED_IDENTITY_CONFLICT"
    # Backward-compatible legacy value; new service results use a specific conflict.
    REJECTED_CONFLICT = "REJECTED_CONFLICT"
    REJECTED_INVENTORY_STATE = "REJECTED_INVENTORY_STATE"
    RETRYABLE_FAILURE = "RETRYABLE_FAILURE"
    INVARIANT_VIOLATION = "INVARIANT_VIOLATION"


class PositionMaterializationAssociationStatus(str, Enum):
    PENDING = "PENDING"
    ASSOCIATED = "ASSOCIATED"
    REQUIRES_REVIEW = "REQUIRES_REVIEW"
    EXHAUSTED = "EXHAUSTED"


class PositionMaterializationEvidenceStatus(str, Enum):
    PRESENT = "PRESENT"
    ABSENT = "ABSENT"
    CONTRADICTION = "CONTRADICTION"


@dataclass(frozen=True)
class PositionMaterializationAssociationClaim:
    request_id: str
    owner: str
    attempt_count: int
    lease_expires_at: datetime


@dataclass(frozen=True)
class PositionMaterializationAssociationEvidence:
    status: PositionMaterializationEvidenceStatus
    source: str | None = None
    target_id: str | None = None


@dataclass(frozen=True)
class PositionMaterializationAssociationReceipt:
    request_id: str
    target_type: str
    target_id: str
    created_at: datetime
    source_detection_id: str | None = None


@dataclass(frozen=True)
class MaterializePositionResult:
    status: PositionMaterializationStatus
    idempotent_replay: bool = False
    location_id: str | None = None
    public_identifier: str | None = None
    request_id: str | None = None
    error_code: str | None = None
    detail: str | None = None

    @property
    def accepted(self) -> bool:
        return self.status in {
            PositionMaterializationStatus.MATERIALIZED,
            PositionMaterializationStatus.REUSED,
        }
