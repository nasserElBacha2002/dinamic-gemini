"""Domain entity for mobile preliminary CODE_SCAN drafts (diagnostic only)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class MobilePreliminaryDetection:
    id: str
    draft_id: str
    inventory_id: str
    aisle_id: str
    asset_id: str
    client_file_id: str
    status: str
    internal_code: str | None
    quantity: int | None
    quantity_status: str | None
    detected_format: str | None
    detected_symbology: str | None
    candidate_count: int
    parser_version: str
    detector_version: str
    prepared_asset_sha256: str
    payload_hash: str | None
    processing_ms: int | None
    detected_at: datetime | None
    received_at: datetime
    validation_status: str
    validation_error_code: str | None
    schema_version: str
    created_at: datetime
    updated_at: datetime
