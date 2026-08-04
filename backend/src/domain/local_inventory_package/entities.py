"""Domain entities for local inventory ZIP package imports."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from src.domain.local_csv_import.entities import LocalCsvImport


@dataclass(frozen=True)
class LocalInventoryPackagePhoto:
    id: str
    package_id: str
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
    staging_path: str
    source_asset_id: str | None = None


@dataclass(frozen=True)
class LocalInventoryPackage:
    id: str
    inventory_id: str
    export_id: str
    csv_import_id: str
    package_kind: str
    package_version: int
    status: str
    package_checksum_sha256: str | None
    csv_checksum_sha256: str
    expected_photo_count: int
    included_photo_count: int
    aisle_id: str | None
    capture_session_id: str | None
    freeze_id: str | None
    staging_dir: str
    created_at: datetime
    updated_at: datetime
    confirmed_at: datetime | None = None
    confirmed_by_user_id: str | None = None
    photos: tuple[LocalInventoryPackagePhoto, ...] = field(default_factory=tuple)
    csv_import: LocalCsvImport | None = None
