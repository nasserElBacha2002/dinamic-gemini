"""List job image coverage — photos from job_source_assets with SQL pagination."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from src.application.errors import (
    InventoryNotFoundError,
    JobDoesNotBelongToAisleError,
    JobNotFoundError,
    PhotosJobRequiredError,
)
from src.application.ports.job_image_coverage_repository import JobImageCoverageRepository
from src.application.ports.job_source_asset_repository import JobSourceAssetRepository
from src.application.ports.repositories import (
    AisleRepository,
    InventoryRepository,
    JobRepository,
    ProductRecordRepository,
)
from src.application.services.aisle_inventory_scope import require_aisle_scoped_to_inventory
from src.application.services.display_primary_product import select_display_primary_product
from src.application.services.job_image_result_resolution import (
    is_photos_job_snapshot,
    resolve_image_processing_status,
    resolve_result_origin_counts,
)
from src.domain.jobs.entities import Job
from src.domain.positions.entities import Position
from src.domain.products.entities import ProductRecord

ResultStatusFilter = Literal["all", "with_result", "without_result"]


@dataclass
class ListJobImageResultsCommand:
    inventory_id: str
    aisle_id: str
    job_id: str
    result_status: ResultStatusFilter = "all"
    page: int = 1
    page_size: int = 25


@dataclass(frozen=True)
class JobImageResultRow:
    job_source_asset_id: str
    source_asset_id: str
    job_id: str
    original_filename: str | None
    created_at: datetime
    position_order: int
    processing_status: str
    has_result: bool
    result_count: int
    automatic_result_count: int
    manual_result_count: int
    has_manual_result: bool
    positions: tuple[Position, ...]
    primary_products: tuple[ProductRecord | None, ...]


@dataclass(frozen=True)
class JobImageResultCounters:
    total_images: int
    with_result: int
    without_result: int


@dataclass(frozen=True)
class ListJobImageResultsResult:
    items: tuple[JobImageResultRow, ...]
    total_items: int
    page: int
    page_size: int
    counters: JobImageResultCounters
    job: Job


class ListJobImageResultsUseCase:
    def __init__(
        self,
        inventory_repo: InventoryRepository,
        aisle_repo: AisleRepository,
        job_repo: JobRepository,
        job_source_asset_repo: JobSourceAssetRepository,
        coverage_repo: JobImageCoverageRepository,
        product_record_repo: ProductRecordRepository,
    ) -> None:
        self._inventory_repo = inventory_repo
        self._aisle_repo = aisle_repo
        self._job_repo = job_repo
        self._job_source_asset_repo = job_source_asset_repo
        self._coverage_repo = coverage_repo
        self._product_record_repo = product_record_repo

    def execute(self, command: ListJobImageResultsCommand) -> ListJobImageResultsResult:
        inv = self._inventory_repo.get_by_id(command.inventory_id)
        if inv is None:
            raise InventoryNotFoundError(f"Inventory not found: {command.inventory_id}")
        require_aisle_scoped_to_inventory(
            self._aisle_repo,
            inventory_id=command.inventory_id,
            aisle_id=command.aisle_id,
            detail_style="strict",
        )
        job = self._job_repo.get_by_id(command.job_id)
        if job is None:
            raise JobNotFoundError(f"Job not found: {command.job_id}")
        if job.target_type != "aisle" or job.target_id != command.aisle_id:
            raise JobDoesNotBelongToAisleError(
                f"Job {command.job_id} does not belong to aisle {command.aisle_id}"
            )

        links = self._job_source_asset_repo.list_for_job(command.job_id)
        if not is_photos_job_snapshot(links, job):
            raise PhotosJobRequiredError(
                "Image coverage is only supported for photos jobs."
            )

        status_filter = (command.result_status or "all").strip().lower()
        if status_filter not in ("all", "with_result", "without_result"):
            status_filter = "all"

        page = max(1, command.page)
        page_size = max(1, min(command.page_size, 200))

        counters = self._coverage_repo.get_counters(
            job_id=command.job_id,
            aisle_id=command.aisle_id,
        )
        snapshot_page, total_filtered = self._coverage_repo.list_snapshot_page(
            job_id=command.job_id,
            aisle_id=command.aisle_id,
            result_status=status_filter,  # type: ignore[arg-type]
            page=page,
            page_size=page_size,
        )
        asset_ids = tuple(row.source_asset_id for row in snapshot_page)
        linked_by_asset = self._coverage_repo.load_positions_for_assets(
            job_id=command.job_id,
            aisle_id=command.aisle_id,
            source_asset_ids=asset_ids,
        )

        built: list[JobImageResultRow] = []
        for snap in snapshot_page:
            linked = tuple(linked_by_asset.get(snap.source_asset_id, ()))
            result_count = len(linked)
            origin = resolve_result_origin_counts(linked)
            status = resolve_image_processing_status(job=job, result_count=result_count)
            primaries: list[ProductRecord | None] = []
            if linked:
                batch = self._product_record_repo.list_by_position_ids([p.id for p in linked])
                by_pos: dict[str, list[ProductRecord]] = {}
                for pr in batch:
                    by_pos.setdefault(pr.position_id, []).append(pr)
                for p in linked:
                    primaries.append(select_display_primary_product(by_pos.get(p.id, ())))
            built.append(
                JobImageResultRow(
                    job_source_asset_id=snap.job_source_asset_id,
                    source_asset_id=snap.source_asset_id,
                    job_id=snap.job_id,
                    original_filename=snap.original_filename,
                    created_at=snap.created_at,
                    position_order=snap.position_order,
                    processing_status=status.value,
                    has_result=result_count > 0,
                    result_count=result_count,
                    automatic_result_count=origin.automatic_result_count,
                    manual_result_count=origin.manual_result_count,
                    has_manual_result=origin.has_manual_result,
                    positions=linked,
                    primary_products=tuple(primaries),
                )
            )

        return ListJobImageResultsResult(
            items=tuple(built),
            total_items=total_filtered,
            page=page,
            page_size=page_size,
            counters=JobImageResultCounters(
                total_images=counters.total_images,
                with_result=counters.with_result,
                without_result=counters.without_result,
            ),
            job=job,
        )
