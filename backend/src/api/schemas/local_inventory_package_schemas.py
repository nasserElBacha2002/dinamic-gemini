"""API schemas for local inventory ZIP package import."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from src.api.schemas.local_csv_import_schemas import LocalCsvImportResponse


class ConfirmLocalInventoryPackageRequest(BaseModel):
    export_id: str = Field(..., min_length=1)
    conflict_policy: Literal["SKIP", "REJECT"] = "SKIP"


class LocalInventoryPackagePhotoResponse(BaseModel):
    capture_photo_id: str
    client_file_id: str
    sequence_number: int | None
    file_name: str
    mime_type: str
    size_bytes: int
    sha256: str
    width: int | None
    height: int | None
    asset_variant: str
    source_asset_id: str | None = None


class LocalInventoryPackageResponse(BaseModel):
    package_id: str
    export_id: str
    inventory_id: str
    csv_import_id: str
    package_kind: str
    package_version: int
    status: str
    expected_photo_count: int
    included_photo_count: int
    package_checksum_sha256: str | None
    csv_checksum_sha256: str
    aisle_id: str | None
    capture_session_id: str | None
    freeze_id: str | None
    duplicate: bool = False
    created_at: datetime
    confirmed_at: datetime | None = None
    confirmed_by_user_id: str | None = None
    photos: list[LocalInventoryPackagePhotoResponse]
    csv_import: LocalCsvImportResponse | None = None
