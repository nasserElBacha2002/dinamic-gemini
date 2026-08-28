"""Wire contracts for v3 local CSV import."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src.domain.local_csv_import.sources import (
    INGESTION_SOURCE_LOCAL_CSV_IMPORT,
    IngestionSource,
)


class ConfirmLocalCsvImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    export_id: str = Field(min_length=1, max_length=255)
    conflict_policy: Literal["SKIP", "REJECT", "skip", "reject"] = "SKIP"


class LocalCsvImportRowResponse(BaseModel):
    row_number: int
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
    """Detection provenance from CSV column `source`."""
    source: str
    """Server-assigned ingestion channel."""
    ingestion_source: IngestionSource = INGESTION_SOURCE_LOCAL_CSV_IMPORT
    requires_review: bool
    error_code: str | None
    notes: str | None
    status: str
    productive_result_id: str | None = None
    validation_errors: list[str]
    validation_warnings: list[str] = Field(
        description=(
            "Includes csv_formula_neutralized warnings. Formula-like text is apostrophe-prefixed "
            "before persistence so later spreadsheet exports cannot execute it."
        )
    )


class LocalCsvImportResponse(BaseModel):
    import_id: str
    export_id: str
    schema_version: str
    inventory_id: str
    status: str
    total_rows: int
    valid_rows: int
    rejected_rows: int
    duplicate_rows: int
    duplicate: bool = False
    created_at: datetime
    confirmed_at: datetime | None
    confirmed_by_user_id: str | None = None
    rows: list[LocalCsvImportRowResponse]
