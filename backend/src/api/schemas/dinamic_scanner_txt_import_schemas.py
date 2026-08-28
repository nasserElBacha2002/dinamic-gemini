"""API schemas for Dinamic Scanner TXT import."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from src.api.schemas.local_csv_import_schemas import LocalCsvImportResponse


class ConfirmDinamicScannerTxtImportRequest(BaseModel):
    export_id: str = Field(..., min_length=1)
    conflict_policy: Literal["SKIP", "REJECT"] = "SKIP"


class DinamicScannerTxtImportResponse(BaseModel):
    aisle_code: str
    aisle_id: str
    aisle_created: bool
    aisle_will_be_created: bool = False
    positions_imported: int
    products_imported: int
    omitted_records: int
    parse_warnings: list[str] = Field(default_factory=list)
    duplicate: bool = False
    csv_import: LocalCsvImportResponse
