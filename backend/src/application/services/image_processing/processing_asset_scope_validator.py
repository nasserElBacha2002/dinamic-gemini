"""Shared scope validation for Phase 7 processing mutations/reads."""

from __future__ import annotations

from dataclasses import dataclass

from src.application.errors import (
    AssetNotInJobSnapshotError,
    InventoryNotFoundError,
    JobDoesNotBelongToAisleError,
    JobNotFoundError,
)
from src.application.ports.job_source_asset_repository import JobSourceAssetRepository
from src.application.ports.repositories import (
    AisleRepository,
    InventoryRepository,
    JobRepository,
)
from src.application.services.aisle_inventory_scope import require_aisle_scoped_to_inventory
from src.domain.aisle.entities import Aisle
from src.domain.jobs.entities import Job


@dataclass(frozen=True)
class ProcessingAssetScope:
    inventory_id: str
    aisle: Aisle
    job: Job
    asset_id: str


class ProcessingAssetScopeValidator:
    def __init__(
        self,
        *,
        inventory_repo: InventoryRepository,
        aisle_repo: AisleRepository,
        job_repo: JobRepository,
        job_source_asset_repo: JobSourceAssetRepository,
    ) -> None:
        self._inventory_repo = inventory_repo
        self._aisle_repo = aisle_repo
        self._job_repo = job_repo
        self._job_source_asset_repo = job_source_asset_repo

    def validate(
        self,
        *,
        inventory_id: str,
        aisle_id: str,
        job_id: str,
        asset_id: str | None = None,
    ) -> ProcessingAssetScope:
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
        if asset_id is not None:
            if not any(
                link.source_asset_id == asset_id
                for link in self._job_source_asset_repo.list_by_job(job_id)
            ):
                raise AssetNotInJobSnapshotError(
                    f"Asset {asset_id} is not part of job snapshot {job_id}"
                )
        return ProcessingAssetScope(
            inventory_id=inventory_id,
            aisle=aisle,
            job=job,
            asset_id=asset_id or "",
        )


__all__ = ["ProcessingAssetScope", "ProcessingAssetScopeValidator"]
