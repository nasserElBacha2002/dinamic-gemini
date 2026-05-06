"""
CRUD use cases for inventory visual references — v3.2.4.

Closes the missing delete/replace capabilities from the reference-images refactor
without changing the product rule that references only affect future processing runs.
"""

from __future__ import annotations

import logging
from typing import Any

from src.application.errors import (
    InventoryNotFoundError,
    InventoryVisualReferenceNotFoundError,
    UnsupportedAssetTypeError,
    ZeroByteFileError,
)
from src.application.ports.repositories import (
    InventoryRepository,
    InventoryVisualReferenceRepository,
)
from src.application.ports.services import ArtifactStorage
from src.application.use_cases.upload_inventory_visual_references import (
    ALLOWED_MIME_TYPES,
    UploadedVisualReferenceFile,
    _normalize_mime,
)
from src.application.utils.inventory_visual_reference_paths import visual_reference_storage_path
from src.domain.inventory.visual_reference import InventoryVisualReference

logger = logging.getLogger(__name__)


class DeleteInventoryVisualReferenceUseCase:
    def __init__(
        self,
        inventory_repo: InventoryRepository,
        reference_repo: InventoryVisualReferenceRepository,
        artifact_storage: ArtifactStorage,
    ) -> None:
        self._inventory_repo = inventory_repo
        self._reference_repo = reference_repo
        self._artifact_storage = artifact_storage

    def execute(self, inventory_id: str, reference_id: str) -> None:
        inventory = self._inventory_repo.get_by_id(inventory_id)
        if inventory is None:
            raise InventoryNotFoundError(f"Inventory not found: {inventory_id}")
        reference = self._reference_repo.get_by_id(reference_id)
        if reference is None or reference.inventory_id != inventory_id:
            raise InventoryVisualReferenceNotFoundError(
                f"Visual reference not found for inventory {inventory_id}: {reference_id}"
            )

        self._reference_repo.delete(reference_id)
        key_to_delete = (reference.storage_key or reference.storage_path or "").strip()
        if key_to_delete:
            try:
                self._artifact_storage.delete_file(key_to_delete)
            except Exception as cleanup_error:
                logger.warning(
                    "Delete cleanup failed for visual reference file %s: %s",
                    key_to_delete,
                    cleanup_error,
                )


class ReplaceInventoryVisualReferenceUseCase:
    def __init__(
        self,
        inventory_repo: InventoryRepository,
        reference_repo: InventoryVisualReferenceRepository,
        artifact_storage: ArtifactStorage,
    ) -> None:
        self._inventory_repo = inventory_repo
        self._reference_repo = reference_repo
        self._artifact_storage = artifact_storage

    def execute(
        self,
        inventory_id: str,
        reference_id: str,
        file: UploadedVisualReferenceFile,
    ) -> InventoryVisualReference:
        inventory = self._inventory_repo.get_by_id(inventory_id)
        if inventory is None:
            raise InventoryNotFoundError(f"Inventory not found: {inventory_id}")
        current = self._reference_repo.get_by_id(reference_id)
        if current is None or current.inventory_id != inventory_id:
            raise InventoryVisualReferenceNotFoundError(
                f"Visual reference not found for inventory {inventory_id}: {reference_id}"
            )
        if file.size <= 0:
            raise ZeroByteFileError("Empty or zero-byte files are not allowed")

        mime = _normalize_mime(file.content_type)
        if mime not in ALLOWED_MIME_TYPES:
            raise UnsupportedAssetTypeError(
                f"Unsupported image content type for visual reference: {file.content_type}"
            )

        storage_path = visual_reference_storage_path(
            inventory_id=inventory_id,
            reference_id=reference_id,
            mime_type=mime,
        )
        old_storage_key = (current.storage_key or current.storage_path or "").strip()
        new_storage_key = ""
        try:
            put_object = getattr(self._artifact_storage, "put_object", None)
            storage_provider = None
            storage_bucket = None
            content_type = mime
            file_size_bytes = file.size
            etag = None
            if callable(put_object):
                stored: Any = put_object(storage_path, file.file_obj, mime)
                storage_provider = getattr(stored, "storage_provider", None)
                storage_bucket = getattr(stored, "storage_bucket", None)
                new_storage_key = getattr(stored, "storage_key", None) or storage_path
                content_type = getattr(stored, "content_type", None) or mime
                file_size_bytes = int(getattr(stored, "file_size_bytes", file.size) or file.size)
                etag = getattr(stored, "etag", None)
            else:
                file.file_obj.seek(0)
                self._artifact_storage.save_file(storage_path, file.file_obj, mime)
                new_storage_key = storage_path

            updated = InventoryVisualReference(
                id=current.id,
                inventory_id=current.inventory_id,
                filename=file.original_filename or current.filename,
                storage_path=storage_path,
                mime_type=mime,
                file_size=file.size,
                created_at=current.created_at,
                storage_provider=storage_provider,
                storage_bucket=storage_bucket,
                storage_key=new_storage_key,
                content_type=content_type,
                file_size_bytes=file_size_bytes,
                etag=etag,
            )
            self._reference_repo.update(updated)
        except Exception:
            if new_storage_key:
                try:
                    self._artifact_storage.delete_file(new_storage_key)
                except Exception as cleanup_error:
                    logger.warning(
                        "Rollback cleanup failed for replaced visual reference file %s: %s",
                        new_storage_key,
                        cleanup_error,
                    )
            raise

        if old_storage_key and old_storage_key != new_storage_key:
            try:
                self._artifact_storage.delete_file(old_storage_key)
            except Exception as cleanup_error:
                logger.warning(
                    "Post-replace cleanup failed for visual reference file %s: %s",
                    old_storage_key,
                    cleanup_error,
                )
        return updated
