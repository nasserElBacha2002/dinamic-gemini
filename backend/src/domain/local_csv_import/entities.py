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
    #: Physical D1 product label identity; None/empty = legacy row without label.
    label_id: str | None = None
    #: Optional positioning label registry id (client_position_labels.id).
    position_label_id: str | None = None
    #: Optional raw DINAMIC_POSITION JSON payload from the device.
    position_payload_raw: str | None = None

    @property
    def secondary_key(self) -> tuple[str, str]:
        """Import uniqueness key.

        D1 product rows: ``(session, label:<label_id>)`` — many products per photo allowed.
        Position-only: ``(session, pos:<capture_photo_id>)``.
        Legacy product (no label_id): ``(session, photo:<capture_photo_id>)``.
        """
        return local_csv_row_secondary_key(
            capture_session_id=self.capture_session_id,
            capture_photo_id=self.capture_photo_id,
            label_id=self.label_id,
            detection_source=self.detection_source,
        )

    @property
    def source(self) -> str:
        """Deprecated alias for detection_source (CSV column semantics)."""
        return self.detection_source


def local_csv_row_secondary_key(
    *,
    capture_session_id: str,
    capture_photo_id: str,
    label_id: str | None,
    detection_source: str | None,
) -> tuple[str, str]:
    session = (capture_session_id or "").strip()
    lid = (label_id or "").strip().upper()
    if lid:
        return session, f"label:{lid}"
    src = (detection_source or "").strip().upper()
    photo = (capture_photo_id or "").strip()
    if src == "LOCAL_POSITION_LABEL":
        return session, f"pos:{photo}"
    return session, f"photo:{photo}"


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
    """Inventory-visible result applied from a confirmed CSV/package import."""

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
    source_asset_id: str | None = None
    #: Physical D1 product label identity; None = legacy row without label.
    label_id: str | None = None
    #: Optional positioning label registry id (client_position_labels.id).
    position_label_id: str | None = None
    #: Optional raw DINAMIC_POSITION JSON payload from the device.
    position_payload_raw: str | None = None
