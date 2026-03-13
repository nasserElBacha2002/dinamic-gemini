"""
UploadAisleAssets use case — v3.0 Épica 4.

Uploads one or more files (photos/videos) to an aisle, persists SourceAsset records,
and marks the aisle as assets_uploaded. Rejects unsupported content types.

Non-atomic flow: for each file we (1) write to storage, (2) persist SourceAsset,
then (3) mark aisle assets_uploaded once. If a later step fails, earlier steps
may have left partial state (e.g. files on disk without DB rows, or DB rows
without aisle status update). No automatic rollback or compensation in this layer;
callers should treat upload as best-effort when errors occur.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import BinaryIO, List, Sequence
from uuid import uuid4

from src.application.errors import EmptyUploadError, UnsupportedAssetTypeError
from src.application.ports.repositories import AisleRepository, SourceAssetRepository
from src.application.ports.services import ArtifactStorage
from src.application.ports.clock import Clock
from src.application.errors import AisleNotFoundError
from src.domain.aisle.entities import Aisle
from src.domain.assets.entities import SourceAsset, SourceAssetType

logger = logging.getLogger(__name__)


def _detect_asset_type(content_type: str) -> SourceAssetType:
    ct = (content_type or "").strip().lower()
    if ct.startswith("video/"):
        return SourceAssetType.VIDEO
    if ct.startswith("image/"):
        return SourceAssetType.PHOTO
    raise UnsupportedAssetTypeError(f"Unsupported content type: {content_type}")


def _safe_filename(name: str) -> str:
    """Sanitize filename for use in storage path (no path traversal)."""
    base = re.sub(r"[^\w.\-]", "_", (name or "file").strip())
    return base[:200] if base else "file"


@dataclass
class UploadedFile:
    """In-memory representation of a file to upload (framework-agnostic)."""
    original_filename: str
    file_obj: BinaryIO
    content_type: str


class UploadAisleAssetsUseCase:
    def __init__(
        self,
        aisle_repo: AisleRepository,
        asset_repo: SourceAssetRepository,
        artifact_storage: ArtifactStorage,
        clock: Clock,
    ) -> None:
        self._aisle_repo = aisle_repo
        self._asset_repo = asset_repo
        self._artifact_storage = artifact_storage
        self._clock = clock

    def execute(
        self,
        inventory_id: str,
        aisle_id: str,
        files: Sequence[UploadedFile],
    ) -> List[SourceAsset]:
        if not files:
            raise EmptyUploadError("At least one file is required")
        aisle = self._aisle_repo.get_by_id(aisle_id)
        if aisle is None:
            raise AisleNotFoundError(f"Aisle not found: {aisle_id}")
        if aisle.inventory_id != inventory_id:
            raise AisleNotFoundError(
                f"Aisle {aisle_id} does not belong to inventory {inventory_id}"
            )
        now = self._clock.now()
        created: List[SourceAsset] = []
        n_files = len(files)
        logger.info("Uploading %d file(s) to aisle %s", n_files, aisle_id)
        try:
            for uf in files:
                asset_type = _detect_asset_type(uf.content_type)
                asset_id = str(uuid4())
                safe_name = _safe_filename(uf.original_filename)
                storage_path = f"aisles/{aisle_id}/raw/{asset_id}_{safe_name}"
                final_path = self._artifact_storage.save_file(
                    storage_path,
                    uf.file_obj,
                    uf.content_type,
                )
                asset = SourceAsset(
                    id=asset_id,
                    aisle_id=aisle_id,
                    type=asset_type,
                    original_filename=uf.original_filename or "file",
                    storage_path=final_path,
                    mime_type=uf.content_type or "application/octet-stream",
                    uploaded_at=now,
                    metadata_json=None,
                )
                self._asset_repo.save(asset)
                created.append(asset)
            aisle.mark_assets_uploaded(now)
            self._aisle_repo.save(aisle)
            return created
        except Exception:
            if created:
                logger.warning(
                    "Upload partially applied for aisle %s: %d asset(s) persisted; "
                    "storage/DB or aisle status may be inconsistent",
                    aisle_id,
                    len(created),
                )
            raise
