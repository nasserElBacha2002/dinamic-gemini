"""
UploadAisleAssets use case — v3.0 Épica 4.

Uploads one or more files (photos/videos) to an aisle, persists SourceAsset records,
and marks the aisle as assets_uploaded. Rejects unsupported content types.

Non-atomic flow: for each file we (1) write to storage, (2) persist SourceAsset,
then (3) mark aisle assets_uploaded once. If a later step fails, earlier steps
may have left partial state (e.g. files on disk without DB rows, or DB rows
without aisle status update). No automatic rollback or compensation in this layer;
callers should treat upload as best-effort when errors occur.

Materialization is delegated to :class:`src.application.services.aisle_source_asset_materializer.AisleSourceAssetMaterializer`.
"""

from __future__ import annotations

import logging
from typing import List, Sequence

from src.application.dto.uploaded_file import UploadedFile
from src.application.errors import EmptyUploadError
from src.application.services.aisle_inventory_scope import require_aisle_scoped_to_inventory
from src.application.services.aisle_source_asset_materializer import AisleSourceAssetMaterializer
from src.application.services.inventory_status_reconciler import InventoryStatusReconciler
from src.application.ports.clock import Clock
from src.application.ports.repositories import AisleRepository, SourceAssetRepository
from src.application.ports.services import ArtifactStorage
from src.domain.assets.entities import SourceAsset

logger = logging.getLogger(__name__)

# Public re-export: existing imports use ``upload_aisle_assets.UploadedFile``.
__all__ = ["UploadAisleAssetsUseCase", "UploadedFile"]


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
        self._materializer = AisleSourceAssetMaterializer(
            aisle_repo=aisle_repo,
            asset_repo=asset_repo,
            artifact_storage=artifact_storage,
            status_reconciler=status_reconciler,
        )

    def execute(
        self,
        inventory_id: str,
        aisle_id: str,
        files: Sequence[UploadedFile],
    ) -> List[SourceAsset]:
        if not files:
            raise EmptyUploadError("At least one file is required")
        aisle = require_aisle_scoped_to_inventory(
            self._aisle_repo,
            inventory_id=inventory_id,
            aisle_id=aisle_id,
            detail_style="strict",
        )
        now = self._clock.now()
        created: List[SourceAsset] = []
        written_paths: List[str] = []
        n_files = len(files)
        logger.info("Uploading %d file(s) to aisle %s", n_files, aisle_id)
        try:
            for uf in files:
                asset, delete_key = self._materializer.persist_uploaded_file_as_source_asset(
                    aisle_id=aisle_id,
                    uploaded=uf,
                    now=now,
                    metadata_json=None,
                )
                written_paths.append(delete_key)
                created.append(asset)
            # One aisle mark + reconcile per upload batch (not per file); matches pre-refactor semantics.
            self._materializer.finalize_aisle_after_source_assets_changed(
                aisle=aisle,
                inventory_id=inventory_id,
                now=now,
            )
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
            logger.exception(
                "Aisle asset upload failed aisle_id=%s uploaded_count=%d attempted_count=%d",
                aisle_id,
                len(created),
                n_files,
            )
            raise
