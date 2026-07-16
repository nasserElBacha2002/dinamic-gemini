"""In-memory JobImageCoverageRepository for tests and non-SQL modes."""

from __future__ import annotations

from src.application.ports.contracts import PositionListQuery
from src.application.ports.job_image_coverage_repository import (
    JobImageCoverageCounters,
    JobImageCoverageSnapshotRow,
    ResultStatusFilter,
)
from src.application.ports.job_source_asset_repository import JobSourceAssetRepository
from src.application.ports.repositories import PositionRepository, ResultEvidenceRepository
from src.application.services.job_image_result_resolution import (
    index_positions_by_source_asset,
    unique_photo_coverage_images,
)
from src.domain.positions.entities import Position

# Unbounded aisle+job reads for coverage (no silent raw-cap false negatives).
_POSITIONS_PAGE_SIZE = 1_000_000


class MemoryJobImageCoverageRepository:
    def __init__(
        self,
        job_source_asset_repo: JobSourceAssetRepository,
        position_repo: PositionRepository,
        result_evidence_repo: ResultEvidenceRepository,
    ) -> None:
        self._job_source_asset_repo = job_source_asset_repo
        self._position_repo = position_repo
        self._result_evidence_repo = result_evidence_repo

    def _list_positions_for_job(self, *, aisle_id: str, job_id: str) -> list[Position]:
        return list(
            self._position_repo.list_by_aisle_query(
                aisle_id,
                PositionListQuery(
                    page=1,
                    page_size=_POSITIONS_PAGE_SIZE,
                    sort_by="created_at",
                    sort_dir="asc",
                    job_id=job_id,
                ),
            )
        )

    def _coverage_index(
        self, *, job_id: str, aisle_id: str, coverage_asset_ids: frozenset[str]
    ) -> dict[str, list[Position]]:
        if not coverage_asset_ids:
            return {}
        positions = self._list_positions_for_job(aisle_id=aisle_id, job_id=job_id)
        evidence_rows = list(self._result_evidence_repo.list_by_job_id(job_id))
        return index_positions_by_source_asset(
            coverage_asset_ids=coverage_asset_ids,
            result_evidence=evidence_rows,
            positions=positions,
        )

    def _snapshot_rows(
        self, *, job_id: str, aisle_id: str
    ) -> tuple[list[JobImageCoverageSnapshotRow], dict[str, list[Position]]]:
        links = self._job_source_asset_repo.list_for_job(job_id)
        images = unique_photo_coverage_images(links)
        asset_ids = frozenset(img.source_asset_id for img in images)
        by_asset = self._coverage_index(
            job_id=job_id, aisle_id=aisle_id, coverage_asset_ids=asset_ids
        )
        rows = [
            JobImageCoverageSnapshotRow(
                job_source_asset_id=img.job_source_asset_id,
                source_asset_id=img.source_asset_id,
                job_id=img.job_id,
                original_filename=img.original_filename,
                created_at=img.created_at,
                position_order=img.position_order,
                mime_type=img.mime_type,
                storage_key=img.storage_key,
            )
            for img in images
        ]
        return rows, by_asset

    def get_counters(self, *, job_id: str, aisle_id: str) -> JobImageCoverageCounters:
        rows, by_asset = self._snapshot_rows(job_id=job_id, aisle_id=aisle_id)
        with_result = 0
        without_result = 0
        for row in rows:
            if by_asset.get(row.source_asset_id):
                with_result += 1
            else:
                without_result += 1
        return JobImageCoverageCounters(
            total_images=len(rows),
            with_result=with_result,
            without_result=without_result,
        )

    def list_snapshot_page(
        self,
        *,
        job_id: str,
        aisle_id: str,
        result_status: ResultStatusFilter,
        page: int,
        page_size: int,
    ) -> tuple[tuple[JobImageCoverageSnapshotRow, ...], int]:
        rows, by_asset = self._snapshot_rows(job_id=job_id, aisle_id=aisle_id)
        status = (result_status or "all").strip().lower()
        if status == "with_result":
            filtered = [r for r in rows if by_asset.get(r.source_asset_id)]
        elif status == "without_result":
            filtered = [r for r in rows if not by_asset.get(r.source_asset_id)]
        else:
            filtered = rows

        page = max(1, int(page))
        page_size = max(1, min(int(page_size), 200))
        start = (page - 1) * page_size
        page_rows = filtered[start : start + page_size]
        return tuple(page_rows), len(filtered)

    def load_positions_for_assets(
        self,
        *,
        job_id: str,
        aisle_id: str,
        source_asset_ids: tuple[str, ...],
    ) -> dict[str, list[Position]]:
        coverage = frozenset(aid.strip() for aid in source_asset_ids if aid and aid.strip())
        return self._coverage_index(
            job_id=job_id, aisle_id=aisle_id, coverage_asset_ids=coverage
        )

    def has_results_for_asset(
        self,
        *,
        job_id: str,
        aisle_id: str,
        source_asset_id: str,
    ) -> bool:
        asset_id = (source_asset_id or "").strip()
        if not asset_id:
            return False
        by_asset = self._coverage_index(
            job_id=job_id,
            aisle_id=aisle_id,
            coverage_asset_ids=frozenset({asset_id}),
        )
        if by_asset.get(asset_id):
            return True
        # Manual coverage link alone also counts (memory path parity with SQL OR branch).
        # Memory coverage repo does not own manual links; callers also check manual_coverage_repo.
        return False
