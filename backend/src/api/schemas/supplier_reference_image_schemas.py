"""v3 supplier reference image API schemas — Phase C2."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class SupplierReferenceImageResponse(BaseModel):
    """Single supplier-scoped reference image (no internal storage paths).

    Use ``GET .../reference-images/{image_id}/file`` for bytes or signed URLs.
    """

    id: str
    client_supplier_id: str
    filename: str
    mime_type: str
    file_size: int
    content_type: str | None = None
    file_size_bytes: int | None = None
    label: str | None = None
    description: str | None = None
    created_at: datetime
    updated_at: datetime


class SupplierReferenceImagesListResponse(BaseModel):
    items: list[SupplierReferenceImageResponse]


class UploadSupplierReferenceImagesResponse(BaseModel):
    """Response for POST .../reference-images (same shape as list items wrapper).

    Upload semantics: each multipart request may include several ``files`` parts; optional ``label``
    and ``description`` form fields are copied onto **every** created row in ``items`` for that batch.
    """

    items: list[SupplierReferenceImageResponse]


class DeleteSupplierReferenceImageResponse(BaseModel):
    deleted: bool = Field(True, description="True when the DB row was removed.")
    id: str
