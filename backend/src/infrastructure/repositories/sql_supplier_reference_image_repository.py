"""SQL Server implementation of SupplierReferenceImageRepository — Phase C1."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone

from src.application.ports.repositories import SupplierReferenceImageRepository
from src.database.sqlserver import SqlServerClient
from src.domain.client_supplier.reference_image import SupplierReferenceImage
from src.infrastructure.storage.sql_storage_fields import resolved_storage_key_for_row


def _to_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _row_to_supplier_reference_image(row) -> SupplierReferenceImage:
    id_value = getattr(row, "id", None)
    supplier_id = getattr(row, "client_supplier_id", None)
    filename = getattr(row, "filename", None)
    storage_path = (getattr(row, "storage_path", None) or "").strip()
    mime_type = getattr(row, "mime_type", None)
    file_size = getattr(row, "file_size", None)
    storage_provider = (getattr(row, "storage_provider", None) or "").strip() or None
    storage_key = resolved_storage_key_for_row(
        storage_provider=storage_provider,
        storage_key_raw=getattr(row, "storage_key", None),
        storage_path=storage_path,
    )
    content_type = (getattr(row, "content_type", None) or "").strip() or (mime_type or "")
    file_size_bytes = getattr(row, "file_size_bytes", None)
    if file_size_bytes is None:
        file_size_bytes = int(file_size or 0)
    created_at = _to_utc(getattr(row, "created_at", None))
    updated_at = _to_utc(getattr(row, "updated_at", None))
    if not id_value:
        raise ValueError("supplier_reference_images row missing required id")
    if not supplier_id:
        raise ValueError("supplier_reference_images row missing required client_supplier_id")
    if not filename:
        raise ValueError("supplier_reference_images row missing required filename")
    if not storage_path:
        raise ValueError("supplier_reference_images row missing required storage_path")
    if not mime_type:
        raise ValueError("supplier_reference_images row missing required mime_type")
    if file_size is None:
        raise ValueError("supplier_reference_images row missing required file_size")
    if created_at is None:
        raise ValueError("supplier_reference_images row missing required created_at")
    if updated_at is None:
        raise ValueError("supplier_reference_images row missing required updated_at")
    return SupplierReferenceImage(
        id=id_value,
        client_supplier_id=supplier_id,
        filename=filename,
        storage_path=storage_path,
        storage_provider=storage_provider,
        storage_bucket=(getattr(row, "storage_bucket", None) or "").strip() or None,
        storage_key=storage_key or None,
        content_type=content_type or None,
        file_size_bytes=int(file_size_bytes),
        etag=(getattr(row, "etag", None) or "").strip() or None,
        mime_type=mime_type,
        file_size=int(file_size),
        label=(getattr(row, "label", None) or "").strip() or None,
        description=(getattr(row, "description", None) or "").strip() or None,
        created_at=created_at,
        updated_at=updated_at,
    )


class SqlSupplierReferenceImageRepository(SupplierReferenceImageRepository):
    def __init__(self, client: SqlServerClient) -> None:
        self._client = client

    def get_by_id(self, reference_image_id: str) -> SupplierReferenceImage | None:
        with self._client.cursor() as cur:
            cur.execute(
                """
                SELECT id, client_supplier_id, filename, storage_path,
                       storage_provider, storage_bucket, storage_key, content_type, file_size_bytes, etag,
                       mime_type, file_size, label, description, created_at, updated_at
                FROM supplier_reference_images
                WHERE id = ?
                """,
                (reference_image_id,),
            )
            row = cur.fetchone()
        return _row_to_supplier_reference_image(row) if row else None

    def create(self, reference_image: SupplierReferenceImage) -> None:
        created = _to_utc(reference_image.created_at)
        updated = _to_utc(reference_image.updated_at)
        if created is None:
            raise ValueError("SupplierReferenceImage.created_at is required")
        if updated is None:
            raise ValueError("SupplierReferenceImage.updated_at is required")
        with self._client.cursor() as cur:
            cur.execute(
                """
                INSERT INTO supplier_reference_images (
                    id, client_supplier_id, filename, storage_path,
                    storage_provider, storage_bucket, storage_key, content_type, file_size_bytes, etag,
                    mime_type, file_size, label, description, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    reference_image.id,
                    reference_image.client_supplier_id,
                    reference_image.filename,
                    reference_image.storage_path,
                    reference_image.storage_provider,
                    reference_image.storage_bucket,
                    reference_image.storage_key,
                    reference_image.content_type,
                    reference_image.file_size_bytes,
                    reference_image.etag,
                    reference_image.mime_type,
                    reference_image.file_size,
                    reference_image.label,
                    reference_image.description,
                    created,
                    updated,
                ),
            )

    def create_many(self, reference_images: Sequence[SupplierReferenceImage]) -> None:
        if not reference_images:
            return
        with self._client.cursor() as cur:
            for image in reference_images:
                created = _to_utc(image.created_at)
                updated = _to_utc(image.updated_at)
                if created is None:
                    raise ValueError("SupplierReferenceImage.created_at is required")
                if updated is None:
                    raise ValueError("SupplierReferenceImage.updated_at is required")
                cur.execute(
                    """
                    INSERT INTO supplier_reference_images (
                        id, client_supplier_id, filename, storage_path,
                        storage_provider, storage_bucket, storage_key, content_type, file_size_bytes, etag,
                        mime_type, file_size, label, description, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        image.id,
                        image.client_supplier_id,
                        image.filename,
                        image.storage_path,
                        image.storage_provider,
                        image.storage_bucket,
                        image.storage_key,
                        image.content_type,
                        image.file_size_bytes,
                        image.etag,
                        image.mime_type,
                        image.file_size,
                        image.label,
                        image.description,
                        created,
                        updated,
                    ),
                )

    def list_by_supplier(self, client_supplier_id: str) -> Sequence[SupplierReferenceImage]:
        with self._client.cursor() as cur:
            cur.execute(
                """
                SELECT id, client_supplier_id, filename, storage_path,
                       storage_provider, storage_bucket, storage_key, content_type, file_size_bytes, etag,
                       mime_type, file_size, label, description, created_at, updated_at
                FROM supplier_reference_images
                WHERE client_supplier_id = ?
                ORDER BY created_at ASC, id ASC
                """,
                (client_supplier_id,),
            )
            rows = cur.fetchall()
        return [_row_to_supplier_reference_image(row) for row in rows]

    def delete(self, reference_image_id: str) -> None:
        with self._client.cursor() as cur:
            cur.execute(
                "DELETE FROM supplier_reference_images WHERE id = ?",
                (reference_image_id,),
            )
