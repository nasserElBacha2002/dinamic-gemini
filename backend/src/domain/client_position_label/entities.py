"""Client-scoped positioning labels — no inventory/aisle ownership."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any


class ClientPositionLabelStatus(str, Enum):
    ACTIVE = "ACTIVE"
    INVALIDATED = "INVALIDATED"


class ClientPositionLabelSignatureStatus(str, Enum):
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
    UNSIGNED = "UNSIGNED"
    SIGNED = "SIGNED"


@dataclass
class ClientPositionLabel:
    id: str
    client_id: str
    public_identifier: str
    name: str
    normalized_name: str
    status: ClientPositionLabelStatus
    payload_version: int
    canonical_payload: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    description: str | None = None
    payload_hash: str | None = None
    signature: str | None = None
    signature_algorithm: str | None = None
    signature_key_version: int | None = None
    signature_status: ClientPositionLabelSignatureStatus = (
        ClientPositionLabelSignatureStatus.UNSIGNED
    )
    created_by: str | None = None
    invalidated_at: datetime | None = None
    invalidation_reason: str | None = None
    idempotency_key: str | None = None
    idempotency_request_hash: str | None = None
    pallet: str | None = None
    side: str | None = None
    level: int | None = None
    marker_index: int | None = None
    marker_total: int | None = None


@dataclass
class ClientPositionLabelArtifact:
    id: str
    label_id: str
    format: str
    preset: str
    template_version: int
    marker_version: int
    content_type: str
    file_size_bytes: int
    artifact_hash: str
    storage_key: str
    created_at: datetime


def normalize_position_label_name(name: str) -> str:
    return " ".join((name or "").strip().split()).upper()
