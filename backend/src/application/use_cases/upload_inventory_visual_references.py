"""
Upload inventory visual references — v3.2.4.

Uploads one or more image files as visual references for an inventory, using
the InventoryVisualReferenceRepository and ArtifactStorage. Enforces:
- inventory existence
- allowed mime types
- maximum references per inventory (config: 3)
- no zero-byte files

Atomicity: All validations (count, mime, size) run before any file is written.
If storage write or DB create fails mid-batch, already-written files are
best-effort removed via ArtifactStorage.delete_file to minimize partial artifacts.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, BinaryIO
from uuid import uuid4

from src.application.errors import (
    EmptyUploadError,
    InventoryNotFoundError,
    MaxInventoryVisualReferencesExceededError,
    UnsupportedAssetTypeError,
    ZeroByteFileError,
)
from src.application.ports.clock import Clock
from src.application.ports.repositories import (
    InventoryRepository,
    InventoryVisualReferenceRepository,
)
from src.application.ports.services import ArtifactStorage
from src.application.utils.inventory_visual_reference_paths import visual_reference_storage_path
from src.domain.inventory.visual_reference import InventoryVisualReference

logger = logging.getLogger(__name__)

MAX_REFERENCES_PER_INVENTORY = 3

ALLOWED_MIME_TYPES = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
}


@dataclass
class UploadedVisualReferenceFile:
    """In-memory representation of a visual reference file (framework-agnostic).

    size must be set by the caller (e.g. API layer after reading content).
    """

    original_filename: str
    file_obj: BinaryIO
    content_type: str
    size: int


def _normalize_mime(mime: str) -> str:
    raw = (mime or "").strip().lower()
    # Strip parameters like "; charset=binary"
    return raw.split(";", 1)[0].strip()


class UploadInventoryVisualReferencesUseCase:
    def __init__(
        self,
        inventory_repo: InventoryRepository,
        reference_repo: InventoryVisualReferenceRepository,
        artifact_storage: ArtifactStorage,
        clock: Clock,
        max_references_per_inventory: int = MAX_REFERENCES_PER_INVENTORY,
    ) -> None:
        self._inventory_repo = inventory_repo
        self._reference_repo = reference_repo
        self._artifact_storage = artifact_storage
        self._clock = clock
        self._max_refs = max_references_per_inventory

    def execute(
        self,
        inventory_id: str,
        files: Sequence[UploadedVisualReferenceFile],
    ) -> list[InventoryVisualReference]:
        if not files:
            raise EmptyUploadError("At least one file is required")
        inventory = self._inventory_repo.get_by_id(inventory_id)
        if inventory is None:
            raise InventoryNotFoundError(f"Inventory not found: {inventory_id}")

        existing = self._reference_repo.list_by_inventory(inventory_id)
        existing_count = len(existing)
        if existing_count + len(files) > self._max_refs:
            raise MaxInventoryVisualReferencesExceededError(
                f"Maximum visual references exceeded for inventory {inventory_id}: "
                f"{existing_count} existing, {len(files)} new, limit {self._max_refs}"
            )

        # Validate all files up front (mime, zero-byte) so we fail before writing any.
        for f in files:
            if f.size <= 0:
                raise ZeroByteFileError("Empty or zero-byte files are not allowed")
            mime = _normalize_mime(f.content_type)
            if mime not in ALLOWED_MIME_TYPES:
                raise UnsupportedAssetTypeError(
                    f"Unsupported image content type for visual reference: {f.content_type}"
                )

        now = self._clock.now()
        created: list[InventoryVisualReference] = []
        written_paths: list[str] = []
        logger.info(
            "Uploading %d visual reference(s) for inventory %s (existing=%d, max=%d)",
            len(files),
            inventory_id,
            existing_count,
            self._max_refs,
        )

        try:
            # 1) Write all files first. If this fails, there are no DB writes to rollback.
            for f in files:
                mime = _normalize_mime(f.content_type)
                reference_id = str(uuid4())
                storage_path = visual_reference_storage_path(
                    inventory_id=inventory_id,
                    reference_id=reference_id,
                    mime_type=mime,
                )
                storage_provider = None
                storage_bucket = None
                storage_key = None
                content_type = mime
                file_size_bytes = f.size
                etag = None
                put_object = getattr(self._artifact_storage, "put_object", None)
                logger.info(
                    "Visual reference upload start inventory_id=%s reference_id=%s target_key=%s content_type=%s",
                    inventory_id,
                    reference_id,
                    storage_path,
                    mime,
                )
                if callable(put_object):
                    logger.info(
                        "Visual reference upload write path=put_object target_key=%s",
                        storage_path,
                    )
                    stored: Any = put_object(storage_path, f.file_obj, mime)
                    storage_provider = getattr(stored, "storage_provider", None)
                    storage_bucket = getattr(stored, "storage_bucket", None)
                    storage_key = getattr(stored, "storage_key", None)
                    content_type = getattr(stored, "content_type", None) or mime
                    file_size_bytes = int(getattr(stored, "file_size_bytes", f.size) or f.size)
                    etag = getattr(stored, "etag", None)
                else:
                    # Legacy adapter compatibility
                    logger.info(
                        "Visual reference upload write path=save_file target_key=%s",
                        storage_path,
                    )
                    self._artifact_storage.save_file(storage_path, f.file_obj, mime)
                    storage_key = storage_path
                logger.info(
                    "Visual reference upload success inventory_id=%s reference_id=%s storage_provider=%s storage_bucket=%s storage_key=%s file_size_bytes=%s etag=%s",
                    inventory_id,
                    reference_id,
                    storage_provider or "local",
                    storage_bucket or "",
                    storage_key or storage_path,
                    file_size_bytes if file_size_bytes is not None else "",
                    etag or "",
                )
                written_paths.append(storage_key or storage_path)
                created.append(
                    InventoryVisualReference(
                        id=reference_id,
                        inventory_id=inventory_id,
                        filename=f.original_filename or "file",
                        storage_path=storage_path,
                        mime_type=mime,
                        file_size=f.size,
                        created_at=now,
                        storage_provider=storage_provider,
                        storage_bucket=storage_bucket,
                        storage_key=storage_key or storage_path,
                        content_type=content_type,
                        file_size_bytes=file_size_bytes,
                        etag=etag,
                    )
                )

            # 2) Persist DB records in a batch (transactional in SQL impl; atomic in memory impl).
            self._reference_repo.create_many(created)
        except Exception:
            # Best-effort rollback of any files written in this batch.
            for p in reversed(written_paths):
                try:
                    self._artifact_storage.delete_file(p)
                except Exception as cleanup_e:
                    logger.warning(
                        "Rollback cleanup failed for visual reference file %s: %s",
                        p,
                        cleanup_e,
                    )
            logger.exception(
                "Visual reference upload failed inventory_id=%s uploaded_count=%d attempted_count=%d",
                inventory_id,
                len(created),
                len(files),
            )
            raise

        return created


class ListInventoryVisualReferencesUseCase:
    def __init__(
        self,
        inventory_repo: InventoryRepository,
        reference_repo: InventoryVisualReferenceRepository,
    ) -> None:
        self._inventory_repo = inventory_repo
        self._reference_repo = reference_repo

    def execute(self, inventory_id: str) -> Sequence[InventoryVisualReference]:
        inventory = self._inventory_repo.get_by_id(inventory_id)
        if inventory is None:
            raise InventoryNotFoundError(f"Inventory not found: {inventory_id}")
        return self._reference_repo.list_by_inventory(inventory_id)
