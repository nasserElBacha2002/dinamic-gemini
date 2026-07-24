"""Authoritative operator-confirmed local CODE_SCAN results."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class AuthoritativeResultSource(str, Enum):
    LOCAL_CODE_SCAN = "LOCAL_CODE_SCAN"
    LOCAL_MANUAL_CORRECTION = "LOCAL_MANUAL_CORRECTION"
    SERVER_CODE_SCAN = "SERVER_CODE_SCAN"
    SERVER_REPROCESS = "SERVER_REPROCESS"


class AuthoritativeQuantityStatus(str, Enum):
    PRESENT = "PRESENT"
    MISSING = "MISSING"


@dataclass(frozen=True)
class AuthoritativeLocalCodeScanResult:
    id: str
    asset_id: str
    inventory_id: str
    aisle_id: str
    client_file_id: str
    result_version: int
    supersedes_result_id: str | None
    is_current: bool
    internal_code: str
    quantity: int | None
    quantity_status: str
    source: str
    detected_internal_code: str | None
    detected_quantity: int | None
    detected_symbology: str | None
    parser_version: str
    detector_version: str
    prepared_asset_sha256: str
    content_hash: str
    confirmed_by: str
    confirmed_at: datetime
    applied_job_id: str | None
    applied_at: datetime | None
    row_version: int
    schema_version: str
    created_at: datetime
    updated_at: datetime
