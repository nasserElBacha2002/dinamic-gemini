"""List job image coverage — photos from job_source_assets LEFT JOIN positions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from src.application.errors import (
    InventoryNotFoundError,
    JobDoesNotBelongToAisleError,
    JobNotFoundError,
    PhotosJobRequiredError,
)
from src.application.ports.contracts import PositionListQuery
from src.application.ports.job_source_asset_repository import JobSourceAssetRepository
from src.application.ports.manual_image_coverage_repository import ManualImageCoverageRepository
from src.application.ports.repositories import (
    AisleRepository,
    InventoryRepository,
    JobRepository,
    PositionRepository,
    ProductRecordRepository,
    ResultEvidenceRepository,
)
from src.application.services.aisle_inventory_scope import require_aisle_scoped_to_inventory
from src.application.services.display_primary_product import select_display_primary_product
from src.application.services.job_image_result_resolution import (
    index_positions_by_source_asset,
    is_photos_job_snapshot,
    resolve_image_processing_status,
    unique_photo_coverage_images,
)
from src.domain.jobs.entities import Job
from src.domain.positions.entities import Position, PositionCreationSource
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
    image_id: str
    source_asset_id: str
    job_id: str
    original_filename: str | None
    created_at: object
    processing_status: str
    has_result: bool
    result_count: int
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
        position_repo: PositionRepository,
        product_record_repo: ProductRecordRepository,
        result_evidence_repo: ResultEvidenceRepository,
        manual_coverage_repo: ManualImageCoverageRepository,
        *,
        positions_raw_cap: int = 10_000,
    ) -> None:
        self._inventory_repo = inventory_repo
        self._aisle_repo = aisle_repo
        self._job_repo = job_repo
        self._job_source_asset_repo = job_source_asset_repo
        self._position_repo = position_repo
        self._product_record_repo = product_record_repo
        self._result_evidence_repo = result_evidence_repo
        self._manual_coverage_repo = manual_coverage_repo
        self._raw_cap = max(1, int(positions_raw_cap))

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

        images = unique_photo_coverage_images(links)
        asset_ids = frozenset(img.source_asset_id for img in images)

        positions = list(
            self._position_repo.list_by_aisle_query(
                command.aisle_id,
                PositionListQuery(
                    page=1,
                    page_size=self._raw_cap,
                    sort_by="created_at",
                    sort_dir="asc",
                    job_id=command.job_id,
                ),
            )
        )
        evidence_rows = list(self._result_evidence_repo.list_by_job_id(command.job_id))
        by_asset = index_positions_by_source_asset(
            coverage_asset_ids=asset_ids,
            result_evidence=evidence_rows,
            positions=positions,
        )
        manual_links = {
            link.source_asset_id: link
            for link in self._manual_coverage_repo.list_by_job(command.job_id)
        }

        built: list[JobImageResultRow] = []
        with_result = 0
        without_result = 0
        for img in images:
            linked = tuple(by_asset.get(img.source_asset_id, ()))
            result_count = len(linked)
            has_result = result_count > 0
            if has_result:
                with_result += 1
            else:
                without_result += 1
            has_manual = img.source_asset_id in manual_links or any(
                p.creation_source == PositionCreationSource.MANUAL for p in linked
            )
            status = resolve_image_processing_status(
                job=job,
                result_count=result_count,
                has_manual_result=has_manual,
            )
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
                    image_id=img.image_id,
                    source_asset_id=img.source_asset_id,
                    job_id=img.job_id,
                    original_filename=img.original_filename,
                    created_at=img.created_at,
                    processing_status=status.value,
                    has_result=has_result,
                    result_count=result_count,
                    positions=linked,
                    primary_products=tuple(primaries),
                )
            )

        status_filter = (command.result_status or "all").strip().lower()
        if status_filter == "with_result":
            filtered = [row for row in built if row.has_result]
        elif status_filter == "without_result":
            filtered = [row for row in built if not row.has_result]
        else:
            filtered = built

        page = max(1, command.page)
        page_size = max(1, min(command.page_size, 200))
        total = len(filtered)
        start = (page - 1) * page_size
        page_rows = filtered[start : start + page_size]

        return ListJobImageResultsResult(
            items=tuple(page_rows),
            total_items=total,
            page=page,
            page_size=page_size,
            counters=JobImageResultCounters(
                total_images=len(built),
                with_result=with_result,
                without_result=without_result,
            ),
            job=job,
        )
