"""Batch reader for final item results associated with job assets."""

from __future__ import annotations

from dataclasses import dataclass

from src.application.ports.job_image_coverage_repository import JobImageCoverageRepository
from src.application.ports.repositories import ProductRecordRepository


@dataclass(frozen=True)
class FinalItemResultRef:
    result_id: str
    source_asset_id: str


class JobFinalItemResultReader:
    def __init__(
        self,
        *,
        coverage_repo: JobImageCoverageRepository,
        product_record_repo: ProductRecordRepository,
    ) -> None:
        self._coverage = coverage_repo
        self._products = product_record_repo

    def list_for_job(
        self,
        *,
        job_id: str,
        aisle_id: str,
        asset_ids: tuple[str, ...],
    ) -> list[FinalItemResultRef]:
        positions_by_asset = self._coverage.load_positions_for_assets(
            job_id=job_id,
            aisle_id=aisle_id,
            source_asset_ids=asset_ids,
        )
        asset_by_position = {
            position.id: asset_id
            for asset_id, positions in positions_by_asset.items()
            for position in positions
        }
        products = self._products.list_by_position_ids(tuple(asset_by_position))
        return sorted(
            (
                FinalItemResultRef(
                    result_id=product.id,
                    source_asset_id=asset_by_position[product.position_id],
                )
                for product in products
                if product.position_id in asset_by_position
            ),
            key=lambda row: (row.source_asset_id, row.result_id),
        )
