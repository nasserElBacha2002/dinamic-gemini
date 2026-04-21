"""
Single spine for persisting aisle SourceAsset rows from uploaded bytes — Sprint 1.

Centralizes storage write, SourceAsset construction, repository save, and the shared
post-batch hooks used by manual upload (``mark_assets_uploaded`` + inventory reconcile).
Future capture-session confirmation should call :meth:`persist_uploaded_file_as_source_asset`
per item and :meth:`finalize_aisle_after_source_assets_changed` once per batch.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from uuid import uuid4

from src.application.dto.uploaded_file import UploadedFile
from src.application.errors import UnsupportedAssetTypeError
from src.application.ports.repositories import AisleRepository, SourceAssetRepository
from src.application.ports.services import ArtifactStorage
from src.application.services.inventory_status_reconciler import InventoryStatusReconciler
from src.domain.aisle.entities import Aisle
from src.domain.assets.entities import SourceAsset, SourceAssetType

logger = logging.getLogger(__name__)

_VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}
_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".heic", ".heif", ".gif", ".tiff"}


def _detect_asset_type(content_type: str) -> SourceAssetType:
    ct = (content_type or "").strip().lower()
    if ct.startswith("video/"):
        return SourceAssetType.VIDEO
    if ct.startswith("image/"):
        return SourceAssetType.PHOTO
    raise UnsupportedAssetTypeError(f"Unsupported content type: {content_type}")


def _safe_filename(name: str) -> str:
    base = re.sub(r"[^\w.\-]", "_", (name or "file").strip())
    return base[:200] if base else "file"


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


def validate_staging_media_upload_file(uploaded: UploadedFile) -> None:
    """Apply the same image/video content-type rules as aisle SourceAsset uploads without persisting assets."""
    asset_type = _detect_asset_type(uploaded.content_type)
    _validate_filename_matches_type(uploaded.original_filename, asset_type)


class AisleSourceAssetMaterializer:
    def __init__(
        self,
        *,
        aisle_repo: AisleRepository,
        asset_repo: SourceAssetRepository,
        artifact_storage: ArtifactStorage,
        status_reconciler: InventoryStatusReconciler,
    ) -> None:
        self._aisle_repo = aisle_repo
        self._asset_repo = asset_repo
        self._artifact_storage = artifact_storage
        self._status_reconciler = status_reconciler

    def persist_uploaded_file_as_source_asset(
        self,
        *,
        aisle_id: str,
        uploaded: UploadedFile,
        now: datetime,
        metadata_json: Optional[Dict[str, Any]] = None,
    ) -> Tuple[SourceAsset, str]:
        """Write bytes to final storage, save ``SourceAsset``, return (entity, rollback_delete_key).

        ``rollback_delete_key`` is the key passed to ``ArtifactStorage.delete_file`` on best-effort
        cleanup (matches legacy upload semantics).
        """
        asset_type = _detect_asset_type(uploaded.content_type)
        _validate_filename_matches_type(uploaded.original_filename, asset_type)
        asset_id = str(uuid4())
        safe_name = _safe_filename(uploaded.original_filename)
        storage_path = f"uploads/aisles/{aisle_id}/raw/{asset_id}_{safe_name}"
        storage_provider = None
        storage_bucket = None
        storage_key = None
        content_type = uploaded.content_type or "application/octet-stream"
        file_size_bytes = None
        etag = None
        put_object = getattr(self._artifact_storage, "put_object", None)
        logger.info(
            "Aisle asset materialize start aisle_id=%s asset_id=%s target_key=%s content_type=%s",
            aisle_id,
            asset_id,
            storage_path,
            content_type,
        )
        if callable(put_object):
            logger.info("Aisle asset materialize write path=put_object target_key=%s", storage_path)
            stored: Any = put_object(storage_path, uploaded.file_obj, content_type)
            storage_provider = getattr(stored, "storage_provider", None)
            storage_bucket = getattr(stored, "storage_bucket", None)
            storage_key = getattr(stored, "storage_key", None)
            content_type = getattr(stored, "content_type", None) or content_type
            file_size_bytes = getattr(stored, "file_size_bytes", None)
            etag = getattr(stored, "etag", None)
        else:
            logger.info("Aisle asset materialize write path=save_file target_key=%s", storage_path)
            self._artifact_storage.save_file(storage_path, uploaded.file_obj, content_type)
            storage_key = storage_path
        delete_key = storage_key or storage_path
        logger.info(
            "Aisle asset materialize success aisle_id=%s asset_id=%s storage_provider=%s storage_bucket=%s storage_key=%s",
            aisle_id,
            asset_id,
            storage_provider or "local",
            storage_bucket or "",
            delete_key,
        )
        asset = SourceAsset(
            id=asset_id,
            aisle_id=aisle_id,
            type=asset_type,
            original_filename=uploaded.original_filename or "file",
            storage_path=storage_path,
            mime_type=content_type,
            uploaded_at=now,
            metadata_json=metadata_json,
            storage_provider=storage_provider,
            storage_bucket=storage_bucket,
            storage_key=delete_key,
            content_type=content_type,
            file_size_bytes=file_size_bytes,
            etag=etag,
        )
        self._asset_repo.save(asset)
        return asset, delete_key

    def finalize_aisle_after_source_assets_changed(
        self,
        *,
        aisle: Aisle,
        inventory_id: str,
        now: datetime,
    ) -> None:
        """Mark aisle as having uploads and reconcile inventory status (manual upload parity)."""
        aisle.mark_assets_uploaded(now)
        self._aisle_repo.save(aisle)
        self._status_reconciler.reconcile(inventory_id)
