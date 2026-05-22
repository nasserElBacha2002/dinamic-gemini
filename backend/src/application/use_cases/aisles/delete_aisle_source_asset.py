"""
Delete one aisle source asset (uploaded photo/video) — v3 operator UI.

Removes the DB row and best-effort deletes the stored object. Blocks mutation while an aisle job
is actively queued or running. When the last asset is removed and the aisle was only in
``assets_uploaded``, status reverts to ``created`` and inventory status is reconciled.
"""

from __future__ import annotations

import logging

from src.application.errors import (
    AisleSourceAssetMutationBlockedError,
    SourceAssetNotFoundForAisleError,
)
from src.application.ports.clock import Clock
from src.application.ports.repositories import AisleRepository, JobRepository, SourceAssetRepository
from src.application.ports.services import ArtifactStorage
from src.application.services.aisle_inventory_scope import require_aisle_scoped_to_inventory
from src.application.services.inventory_status_reconciler import InventoryStatusReconciler
from src.domain.jobs.entities import JobStatus

logger = logging.getLogger(__name__)

_BLOCKED_JOB_STATUSES: set[JobStatus] = {
    JobStatus.QUEUED,
    JobStatus.STARTING,
    JobStatus.RUNNING,
    JobStatus.CANCEL_REQUESTED,
}


class DeleteAisleSourceAssetUseCase:
    def __init__(
        self,
        aisle_repo: AisleRepository,
        asset_repo: SourceAssetRepository,
        job_repo: JobRepository,
        artifact_storage: ArtifactStorage,
        clock: Clock,
        status_reconciler: InventoryStatusReconciler,
    ) -> None:
        self._aisle_repo = aisle_repo
        self._asset_repo = asset_repo
        self._job_repo = job_repo
        self._artifact_storage = artifact_storage
        self._clock = clock
        self._status_reconciler = status_reconciler

    def _assert_no_active_jobs(self, aisle_id: str) -> None:
        jobs = self._job_repo.list_jobs_for_target("aisle", aisle_id, limit=100)
        for j in jobs:
            if j.status in _BLOCKED_JOB_STATUSES:
                raise AisleSourceAssetMutationBlockedError(
                    f"Aisle {aisle_id} has an active job (status={j.status.value})"
                )

    def execute(self, inventory_id: str, aisle_id: str, asset_id: str) -> None:
        aisle = require_aisle_scoped_to_inventory(
            self._aisle_repo,
            inventory_id=inventory_id,
            aisle_id=aisle_id,
            detail_style="strict",
        )
        self._assert_no_active_jobs(aisle_id)

        asset = self._asset_repo.get_by_id(asset_id)
        if asset is None or asset.aisle_id != aisle_id:
            raise SourceAssetNotFoundForAisleError(
                f"Source asset not found for aisle {aisle_id}: {asset_id}"
            )

        storage_key = (asset.storage_key or asset.storage_path or "").strip()
        deleted_row = self._asset_repo.delete_by_id(asset_id)
        if not deleted_row:
            raise SourceAssetNotFoundForAisleError(
                f"Source asset not found for aisle {aisle_id}: {asset_id}"
            )

        if storage_key:
            try:
                self._artifact_storage.delete_file(storage_key)
            except Exception as cleanup_error:
                logger.warning(
                    "Delete cleanup failed for aisle source asset file %s: %s",
                    storage_key,
                    cleanup_error,
                )

        now = self._clock.now()
        remaining = self._asset_repo.list_by_aisle(aisle_id)
        if len(remaining) == 0 and aisle.revert_to_created_when_no_source_assets_remain(now):
            self._aisle_repo.save(aisle)

        self._status_reconciler.reconcile(inventory_id)
