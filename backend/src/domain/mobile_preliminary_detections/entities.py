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
    expires_at: datetime
    validation_status: str
    validation_error_code: str | None
    schema_version: str
    created_at: datetime
    updated_at: datetime
    position_local_recognition_id: str | None = None
    position_raw_code: str | None = None
    position_claimed_normalized_code: str | None = None
    position_claimed_remote_id: str | None = None
    position_claimed_remote_label_id: str | None = None
    position_source: str | None = None
    position_profile_id: str | None = None
    position_profile_version: int | None = None
    position_client_supplier_id: str | None = None
    position_signature_present: bool | None = None
    position_signature_verification: str | None = None
    position_captured_at: datetime | None = None
    position_result_status: str | None = None
    position_result_error_code: str | None = None
    position_result_retryable: bool | None = None
    position_normalized_code: str | None = None
    position_remote_id: str | None = None
    position_remote_label_id: str | None = None
    position_validated_at: datetime | None = None
    position_reconciliation_revision: int = 0
