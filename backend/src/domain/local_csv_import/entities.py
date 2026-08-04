"""Audit and row-result entities for versioned local CSV imports."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from src.domain.local_csv_import.sources import INGESTION_SOURCE_LOCAL_CSV_IMPORT

# Backward-compatible alias used by routes/tests.
LOCAL_CSV_IMPORT_SOURCE = INGESTION_SOURCE_LOCAL_CSV_IMPORT


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
    """Detection provenance from the CSV `source` column (LOCAL_CODE_SCAN, …)."""
    detection_source: str
    """Server-assigned ingestion channel — always LOCAL_CSV_IMPORT."""
    ingestion_source: str
    requires_review: bool
    error_code: str | None
    notes: str | None
    status: str
    validation_errors: tuple[str, ...] = ()
    validation_warnings: tuple[str, ...] = ()
    productive_result_id: str | None = None

    @property
    def secondary_key(self) -> tuple[str, str]:
        return self.capture_session_id, self.capture_photo_id

    @property
    def source(self) -> str:
        """Deprecated alias for detection_source (CSV column semantics)."""
        return self.detection_source


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
    confirmed_by_user_id: str | None = None
    rows: tuple[LocalCsvImportRow, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class LocalCsvProductiveResult:
    """Inventory-visible result applied from a confirmed CSV import (no image evidence)."""

    id: str
    inventory_id: str
    aisle_id: str
    import_id: str
    import_row_id: str
    capture_session_id: str
    capture_photo_id: str
    client_file_id: str
    capture_order: int | None
    position_code: str | None
    internal_code: str | None
    quantity: int | None
    quantity_status: str
    detection_status: str
    detection_source: str
    ingestion_source: str
    requires_review: bool
    has_image_evidence: bool
    confirmed_by_user_id: str | None
    created_at: datetime
    updated_at: datetime
