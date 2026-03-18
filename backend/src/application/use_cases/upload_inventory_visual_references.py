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
from dataclasses import dataclass
from typing import BinaryIO, List, Sequence
from uuid import uuid4

from src.application.errors import (
    EmptyUploadError,
    InventoryNotFoundError,
    MaxInventoryVisualReferencesExceededError,
    UnsupportedAssetTypeError,
    ZeroByteFileError,
)
from src.application.ports.clock import Clock
from src.application.ports.repositories import InventoryRepository, InventoryVisualReferenceRepository
from src.application.ports.services import ArtifactStorage
from src.domain.inventory.visual_reference import InventoryVisualReference
from src.infrastructure.storage.inventory_visual_reference_paths import visual_reference_storage_path

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
    ) -> List[InventoryVisualReference]:
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
                raise UnsupportedAssetTypeError(f"Unsupported image content type for visual reference: {f.content_type}")

        now = self._clock.now()
        created: List[InventoryVisualReference] = []
        written_paths: List[str] = []
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
                final_path = self._artifact_storage.save_file(storage_path, f.file_obj, mime)
                written_paths.append(final_path)
                created.append(
                    InventoryVisualReference(
                        id=reference_id,
                        inventory_id=inventory_id,
                        filename=f.original_filename or "file",
                        storage_path=final_path,
                        mime_type=mime,
                        file_size=f.size,
                        created_at=now,
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

