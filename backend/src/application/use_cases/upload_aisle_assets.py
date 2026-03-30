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
from pathlib import Path
from typing import Any, BinaryIO, List, Sequence
from uuid import uuid4

from src.application.errors import EmptyUploadError, UnsupportedAssetTypeError
from src.application.services.inventory_status_reconciler import InventoryStatusReconciler
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


_VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}
_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".heic", ".heif", ".gif", ".tiff"}


def _validate_filename_matches_type(filename: str, asset_type: SourceAssetType) -> None:
    ext = Path(filename or "").suffix.strip().lower()
    if not ext:
        return
    if asset_type == SourceAssetType.PHOTO and ext in _VIDEO_EXTS:
        raise UnsupportedAssetTypeError(
            f"Invalid photo upload: file extension {ext} indicates video ({filename})"
        )
    if asset_type == SourceAssetType.VIDEO and ext in _IMAGE_EXTS:
        raise UnsupportedAssetTypeError(
            f"Invalid video upload: file extension {ext} indicates image ({filename})"
        )


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
        status_reconciler: InventoryStatusReconciler,
    ) -> None:
        self._aisle_repo = aisle_repo
        self._asset_repo = asset_repo
        self._artifact_storage = artifact_storage
        self._clock = clock
        self._status_reconciler = status_reconciler

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
        written_paths: List[str] = []
        n_files = len(files)
        logger.info("Uploading %d file(s) to aisle %s", n_files, aisle_id)
        try:
            for uf in files:
                asset_type = _detect_asset_type(uf.content_type)
                _validate_filename_matches_type(uf.original_filename, asset_type)
                asset_id = str(uuid4())
                safe_name = _safe_filename(uf.original_filename)
                storage_path = f"uploads/aisles/{aisle_id}/raw/{asset_id}_{safe_name}"
                storage_provider = None
                storage_bucket = None
                storage_key = None
                content_type = uf.content_type or "application/octet-stream"
                file_size_bytes = None
                etag = None
                put_object = getattr(self._artifact_storage, "put_object", None)
                if callable(put_object):
                    stored: Any = put_object(storage_path, uf.file_obj, content_type)
                    storage_provider = getattr(stored, "storage_provider", None)
                    storage_bucket = getattr(stored, "storage_bucket", None)
                    storage_key = getattr(stored, "storage_key", None)
                    content_type = getattr(stored, "content_type", None) or content_type
                    file_size_bytes = getattr(stored, "file_size_bytes", None)
                    etag = getattr(stored, "etag", None)
                else:
                    # Legacy adapter compatibility
                    self._artifact_storage.save_file(storage_path, uf.file_obj, content_type)
                    storage_key = storage_path
                written_paths.append(storage_key or storage_path)
                asset = SourceAsset(
                    id=asset_id,
                    aisle_id=aisle_id,
                    type=asset_type,
                    original_filename=uf.original_filename or "file",
                    storage_path=storage_path,
                    mime_type=content_type,
                    uploaded_at=now,
                    metadata_json=None,
                    storage_provider=storage_provider,
                    storage_bucket=storage_bucket,
                    storage_key=storage_key or storage_path,
                    content_type=content_type,
                    file_size_bytes=file_size_bytes,
                    etag=etag,
                )
                self._asset_repo.save(asset)
                created.append(asset)
            aisle.mark_assets_uploaded(now)
            self._aisle_repo.save(aisle)
            self._status_reconciler.reconcile(inventory_id)
            return created
        except Exception:
            if created:
                logger.warning(
                    "Upload partially applied for aisle %s: %d asset(s) persisted; "
                    "storage/DB or aisle status may be inconsistent",
                    aisle_id,
                    len(created),
                )
            for p in reversed(written_paths):
                try:
                    self._artifact_storage.delete_file(p)
                except Exception as cleanup_e:
                    logger.warning("Rollback cleanup failed for aisle asset file %s: %s", p, cleanup_e)
            raise
