"""Logical positioning label emission — Phase 1 (render deferred to later phases)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any


class AisleLocationLabelStatus(str, Enum):
    ACTIVE = "ACTIVE"
    REPLACED = "REPLACED"
    INVALIDATED = "INVALIDATED"
    ARCHIVED = "ARCHIVED"


class PositioningLabelSignatureStatus(str, Enum):
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
    UNSIGNED = "UNSIGNED"
    SIGNED = "SIGNED"


POSITIONING_LABEL_TYPE = "DINAMIC_POSITION"
POSITIONING_LABEL_PAYLOAD_VERSION = 1


@dataclass
class AisleLocationLabel:
    id: str
    client_id: str
    location_id: str
    public_identifier: str
    payload_version: int
    marker_version: int
    template_version: int
    status: AisleLocationLabelStatus
    payload: dict[str, Any]
    generated_at: datetime
    payload_hash: str | None = None
    signature_status: PositioningLabelSignatureStatus = (
        PositioningLabelSignatureStatus.NOT_IMPLEMENTED
    )
    generated_by: str | None = None
    invalidated_at: datetime | None = None
    invalidation_reason: str | None = None
    replaced_by_label_id: str | None = None
    replaced_at: datetime | None = None
    idempotency_key: str | None = None
    idempotency_request_hash: str | None = None
