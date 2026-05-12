"""Supplier reference image domain entity — Phase C1 foundation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class SupplierReferenceImage:
    """A single reference image owned by a client supplier."""

    id: str
    client_supplier_id: str
    filename: str
    storage_path: str
    mime_type: str
    file_size: int
    created_at: datetime
    updated_at: datetime
    storage_provider: str | None = None
    storage_bucket: str | None = None
    storage_key: str | None = None
    content_type: str | None = None
    file_size_bytes: int | None = None
    etag: str | None = None
    label: str | None = None
    description: str | None = None

    def __post_init__(self) -> None:
        if not self.id or not self.id.strip():
            raise ValueError("SupplierReferenceImage.id is required")
        if not self.client_supplier_id or not self.client_supplier_id.strip():
            raise ValueError("SupplierReferenceImage.client_supplier_id is required")
        if not self.filename or not self.filename.strip():
            raise ValueError("SupplierReferenceImage.filename is required")
        if not self.storage_path or not self.storage_path.strip():
            raise ValueError("SupplierReferenceImage.storage_path is required")
        if not self.mime_type or not self.mime_type.strip():
            raise ValueError("SupplierReferenceImage.mime_type is required")
        if self.file_size is None or self.file_size < 0:
            raise ValueError("SupplierReferenceImage.file_size must be >= 0")
        if self.created_at is None:
            raise ValueError("SupplierReferenceImage.created_at is required")
        if self.updated_at is None:
            raise ValueError("SupplierReferenceImage.updated_at is required")
