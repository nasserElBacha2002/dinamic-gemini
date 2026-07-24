"""Domain entity for preliminary vs remote reconciliation (diagnostic only)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class PreliminaryDetectionReconciliation:
    id: str
    preliminary_detection_id: str
    asset_id: str
    remote_result_id: str | None
    job_id: str
    inventory_id: str
    aisle_id: str
    client_file_id: str
    local_status: str
    local_internal_code: str | None
    local_quantity: int | None
    remote_status: str | None
    remote_internal_code: str | None
    remote_quantity: int | None
    outcome: str
    not_comparable_reason: str | None
    local_parser_version: str | None
    local_detector_version: str | None
    remote_pipeline_version: str | None
    local_detected_at: datetime | None
    remote_completed_at: datetime | None
    compared_at: datetime
    comparison_version: str
    reconciliation_status: str
    created_at: datetime
    updated_at: datetime
    remote_result_fingerprint: str = "PENDING"
    revision: int = 1
    supersedes_id: str | None = None
    row_version: int = 1
    attempt_count: int = 0
    next_retry_at: datetime | None = None
    lease_token: str | None = None
    lease_expires_at: datetime | None = None
    last_error_code: str | None = None
    app_version: str | None = None
    device_model: str | None = None
    preparation_profile: str | None = None
    expires_at: datetime | None = None
