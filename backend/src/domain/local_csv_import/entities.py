"""Audit and row-result entities for versioned local CSV imports."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

LOCAL_CSV_IMPORT_SOURCE = "LOCAL_CSV_IMPORT"


@dataclass(frozen=True)
class LocalCsvImportRow:
    id: str
    import_id: str
    row_number: int
    inventory_id: str
    aisle_id: str
    capture_session_id: str
    capture_photo_id: str
    client_file_id: str
    capture_order: int | None
    captured_at: datetime | None
    position_code: str
    internal_code: str | None
    quantity: int | None
    quantity_status: str
    detection_status: str
    source: str
    requires_review: bool
    error_code: str | None
    notes: str | None
    status: str
    validation_errors: tuple[str, ...] = ()
    validation_warnings: tuple[str, ...] = ()

    @property
    def secondary_key(self) -> tuple[str, str]:
        return self.capture_session_id, self.capture_photo_id


@dataclass(frozen=True)
class LocalCsvImport:
    id: str
    export_id: str
    schema_version: str
    inventory_id: str
    device_id: str
    exported_at: datetime
    status: str
    content_hash: str
    total_rows: int
    valid_rows: int
    rejected_rows: int
    duplicate_rows: int
    created_at: datetime
    updated_at: datetime
    confirmed_at: datetime | None = None
    conflict_policy: str | None = None
    rows: tuple[LocalCsvImportRow, ...] = field(default_factory=tuple)
