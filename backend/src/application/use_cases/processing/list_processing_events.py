"""Phase 7 — list processing events for an asset."""

from __future__ import annotations

from src.application.errors import (
    AssetNotInJobSnapshotError,
    InventoryNotFoundError,
    JobDoesNotBelongToAisleError,
    JobNotFoundError,
)
from src.application.ports.job_source_asset_repository import JobSourceAssetRepository
from src.application.ports.processing_event_repository import ProcessingEventRepository
from src.application.ports.repositories import (
    AisleRepository,
    InventoryRepository,
    JobRepository,
)
from src.application.services.aisle_inventory_scope import require_aisle_scoped_to_inventory
from src.application.services.image_processing.processing_evidence_sanitizer import (
    sanitize_metadata,
)


class ListProcessingEventsUseCase:
    def __init__(
        self,
        *,
        inventory_repo: InventoryRepository,
        aisle_repo: AisleRepository,
        job_repo: JobRepository,
        job_source_asset_repo: JobSourceAssetRepository,
        event_repo: ProcessingEventRepository | None,
    ) -> None:
        self._inventory_repo = inventory_repo
        self._aisle_repo = aisle_repo
        self._job_repo = job_repo
        self._job_source_asset_repo = job_source_asset_repo
        self._event_repo = event_repo

    def execute(
        self,
        *,
        inventory_id: str,
        aisle_id: str,
        job_id: str,
        asset_id: str,
        page: int = 1,
        page_size: int = 50,
    ) -> dict:
        if self._inventory_repo.get_by_id(inventory_id) is None:
            raise InventoryNotFoundError(f"Inventory not found: {inventory_id}")
        aisle = require_aisle_scoped_to_inventory(
            self._aisle_repo, aisle_id=aisle_id, inventory_id=inventory_id
        )
        job = self._job_repo.get_by_id(job_id)
        if job is None:
            raise JobNotFoundError(f"Job not found: {job_id}")
        if job.target_id != aisle.id:
            raise JobDoesNotBelongToAisleError(
                f"Job {job_id} does not belong to aisle {aisle_id}"
            )
        if not any(
            link.source_asset_id == asset_id
            for link in self._job_source_asset_repo.list_by_job(job_id)
        ):
            raise AssetNotInJobSnapshotError(
                f"Asset {asset_id} is not part of job snapshot {job_id}"
            )

        page = max(1, int(page))
        page_size = min(200, max(1, int(page_size)))
        offset = (page - 1) * page_size
        if self._event_repo is None:
            return {
                "items": [],
                "total": 0,
                "page": page,
                "page_size": page_size,
                "has_more": False,
            }
        total = self._event_repo.count_by_job_asset(job_id, asset_id)
        rows = self._event_repo.list_by_job_asset(
            job_id, asset_id, limit=page_size, offset=offset
        )
        items = [
            {
                "id": e.id,
                "event_type": e.event_type,
                "timestamp": e.created_at.isoformat(),
                "level": e.severity,
                "message": e.message,
                "metadata": sanitize_metadata(e.metadata),
            }
            for e in rows
        ]
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "has_more": offset + len(items) < total,
        }


__all__ = ["ListProcessingEventsUseCase"]
