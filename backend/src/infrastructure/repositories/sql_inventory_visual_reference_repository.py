"""
SQL Server implementation of InventoryVisualReferenceRepository — v3.2.4.

Persists InventoryVisualReference entities. Requires inventory_visual_references table.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional, Sequence

from src.application.ports.repositories import InventoryVisualReferenceRepository
from src.database.sqlserver import SqlServerClient
from src.domain.inventory.visual_reference import InventoryVisualReference

logger = logging.getLogger(__name__)


def _to_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Normalize datetime to timezone-aware UTC.

    - Naive datetimes are assumed to be UTC and get tzinfo=UTC.
    - Aware datetimes are converted via astimezone(UTC).
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _row_to_reference(row) -> InventoryVisualReference:
    id_value = getattr(row, "id", None)
    inventory_id = getattr(row, "inventory_id", None)
    filename = getattr(row, "filename", None)
    storage_path = getattr(row, "storage_path", None)
    mime_type = getattr(row, "mime_type", None)
    file_size = getattr(row, "file_size", None)
    storage_path = (getattr(row, "storage_path", None) or "").strip()
    storage_key = (getattr(row, "storage_key", None) or "").strip() or storage_path
    # Canonical media type in current domain/API is mime_type; content_type is transport/storage metadata.
    content_type = (getattr(row, "content_type", None) or "").strip() or (mime_type or "")
    file_size_bytes = getattr(row, "file_size_bytes", None)
    if file_size_bytes is None:
        file_size_bytes = int(file_size or 0)
    created_raw = getattr(row, "created_at", None)

    if not id_value:
        raise ValueError("inventory_visual_references row missing required id")
    if not inventory_id:
        raise ValueError("inventory_visual_references row missing required inventory_id")
    if not filename:
        raise ValueError("inventory_visual_references row missing required filename")
    if not storage_path:
        raise ValueError("inventory_visual_references row missing required storage_path")
    if not mime_type:
        raise ValueError("inventory_visual_references row missing required mime_type")
    if file_size is None:
        raise ValueError("inventory_visual_references row missing required file_size")
    created = _to_utc(created_raw)
    if created is None:
        raise ValueError("inventory_visual_references row missing required created_at")

    return InventoryVisualReference(
        id=id_value,
        inventory_id=inventory_id,
        filename=filename,
        storage_path=storage_path,
        mime_type=mime_type,
        file_size=int(file_size),
        created_at=created,
        storage_provider=(getattr(row, "storage_provider", None) or "").strip() or None,
        storage_bucket=(getattr(row, "storage_bucket", None) or "").strip() or None,
        storage_key=storage_key or None,
        content_type=content_type or None,
        file_size_bytes=int(file_size_bytes),
        etag=(getattr(row, "etag", None) or "").strip() or None,
    )


class SqlInventoryVisualReferenceRepository(InventoryVisualReferenceRepository):
    def __init__(self, client: SqlServerClient) -> None:
        self._client = client

    def create(self, reference: InventoryVisualReference) -> None:
        created = _to_utc(reference.created_at)
        if created is None:
            raise ValueError("InventoryVisualReference.created_at is required")
        with self._client.cursor() as cur:
            cur.execute(
                """
                INSERT INTO inventory_visual_references (
                    id, inventory_id, filename, storage_path,
                    storage_provider, storage_bucket, storage_key, content_type, file_size_bytes, etag,
                    mime_type, file_size, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    reference.id,
                    reference.inventory_id,
                    reference.filename,
                    reference.storage_path,
                    reference.storage_provider,
                    reference.storage_bucket,
                    reference.storage_key,
                    reference.content_type,
                    reference.file_size_bytes,
                    reference.etag,
                    reference.mime_type,
                    reference.file_size,
                    created,
                ),
            )

    def create_many(self, references: Sequence[InventoryVisualReference]) -> None:
        if not references:
            return
        # Single cursor context => single DB transaction (commit on success, rollback on exception).
        with self._client.cursor() as cur:
            for reference in references:
                created = _to_utc(reference.created_at)
                if created is None:
                    raise ValueError("InventoryVisualReference.created_at is required")
                cur.execute(
                    """
                    INSERT INTO inventory_visual_references (
                        id, inventory_id, filename, storage_path,
                        storage_provider, storage_bucket, storage_key, content_type, file_size_bytes, etag,
                        mime_type, file_size, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        reference.id,
                        reference.inventory_id,
                        reference.filename,
                        reference.storage_path,
                        reference.storage_provider,
                        reference.storage_bucket,
                        reference.storage_key,
                        reference.content_type,
                        reference.file_size_bytes,
                        reference.etag,
                        reference.mime_type,
                        reference.file_size,
                        created,
                    ),
                )

    def list_by_inventory(self, inventory_id: str) -> Sequence[InventoryVisualReference]:
        with self._client.cursor() as cur:
            cur.execute(
                """
                SELECT id, inventory_id, filename, storage_path,
                       storage_provider, storage_bucket, storage_key, content_type, file_size_bytes, etag,
                       mime_type, file_size, created_at
                FROM inventory_visual_references
                WHERE inventory_id = ?
                ORDER BY created_at ASC, id ASC
                """,
                (inventory_id,),
            )
            rows = cur.fetchall()
        return [_row_to_reference(row) for row in rows]
