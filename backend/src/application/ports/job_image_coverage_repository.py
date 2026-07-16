"""Read port for SQL-backed job image coverage (pagination + counters)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

from src.domain.positions.entities import Position

ResultStatusFilter = Literal["all", "with_result", "without_result"]


@dataclass(frozen=True)
class JobImageCoverageCounters:
    total_images: int
    with_result: int
    without_result: int


@dataclass(frozen=True)
class JobImageCoverageSnapshotRow:
    job_source_asset_id: str
    source_asset_id: str
    job_id: str
    original_filename: str | None
    created_at: datetime
    position_order: int
    mime_type: str | None
    storage_key: str | None


class JobImageCoverageRepository(Protocol):
    def get_counters(self, *, job_id: str, aisle_id: str) -> JobImageCoverageCounters: ...

    def list_snapshot_page(
        self,
        *,
        job_id: str,
        aisle_id: str,
        result_status: ResultStatusFilter,
        page: int,
        page_size: int,
    ) -> tuple[tuple[JobImageCoverageSnapshotRow, ...], int]: ...

    def load_positions_for_assets(
        self,
        *,
        job_id: str,
        aisle_id: str,
        source_asset_ids: tuple[str, ...],
    ) -> dict[str, list[Position]]: ...
