"""
ListAislesWithStatus use case — v3.0 (Épica 4 correction).

Returns aisles for an inventory with latest job per aisle in one batch.
Sprint 1.3: per-aisle rollups. Sprint 1.4: search, status filter, sort, pagination.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Sequence, Tuple

from src.application.ports.contracts import AisleTableQuery
from src.application.ports.repositories import (
    AisleRepository,
    InventoryRepository,
    JobRepository,
    PositionRepository,
    SourceAssetRepository,
)
from src.application.errors import InventoryNotFoundError
from src.domain.aisle.entities import Aisle
from src.domain.jobs.entities import Job
from src.domain.positions.entities import Position


@dataclass
class AisleWithLatestJob:
    """Aisle plus its latest job and screen-oriented row rollups (list endpoint)."""

    aisle: Aisle
    latest_job: Optional[Job]
    assets_count: int = 0
    positions_count: int = 0
    pending_review_positions_count: int = 0
    last_activity_at: Optional[datetime] = None


def _aisle_last_activity_at(
    aisle: Aisle,
    latest_job: Optional[Job],
    positions: Sequence[Position],
    asset_last_upload: Optional[datetime],
) -> datetime:
    parts: List[datetime] = [aisle.updated_at, aisle.created_at]
    if latest_job is not None:
        parts.extend([latest_job.updated_at, latest_job.created_at])
    for p in positions:
        parts.extend([p.updated_at, p.created_at])
    if asset_last_upload is not None:
        parts.append(asset_last_upload)
    return max(parts)


def _row_sort_key(row: AisleWithLatestJob, sort_by: str) -> tuple:
    sb = (sort_by or "code").strip().lower()
    a = row.aisle
    if sb == "status":
        return (a.status.value, a.code, a.id)
    if sb == "last_activity_at":
        la = row.last_activity_at or a.updated_at
        return (la, a.code, a.id)
    if sb == "pending_review_positions_count":
        return (row.pending_review_positions_count, a.code, a.id)
    if sb == "positions_count":
        return (row.positions_count, a.code, a.id)
    if sb == "assets_count":
        return (row.assets_count, a.code, a.id)
    # code default
    return (a.code.lower(), a.id)


class ListAislesWithStatusUseCase:
    def __init__(
        self,
        inventory_repo: InventoryRepository,
        aisle_repo: AisleRepository,
        job_repo: JobRepository,
        position_repo: PositionRepository,
        source_asset_repo: SourceAssetRepository,
    ) -> None:
        self._inventory_repo = inventory_repo
        self._aisle_repo = aisle_repo
        self._job_repo = job_repo
        self._position_repo = position_repo
        self._source_asset_repo = source_asset_repo

    def execute(
        self, inventory_id: str, query: Optional[AisleTableQuery] = None
    ) -> Tuple[List[AisleWithLatestJob], int]:
        if self._inventory_repo.get_by_id(inventory_id) is None:
            raise InventoryNotFoundError(f"Inventory not found: {inventory_id}")
        q = query or AisleTableQuery()
        aisles = list(self._aisle_repo.list_by_inventory(inventory_id))
        search = (q.search or "").strip().lower() if q.search else None
        if search:
            aisles = [a for a in aisles if search in a.code.lower()]
        if q.status is not None and str(q.status).strip():
            st = str(q.status).strip()
            aisles = [a for a in aisles if a.status.value == st]

        if not aisles:
            return [], 0

        aisle_ids: Sequence[str] = [a.id for a in aisles]
        latest_by_aisle = self._job_repo.get_latest_by_targets("aisle", aisle_ids)
        positions = self._position_repo.list_by_aisles(list(aisle_ids))
        by_aisle_pos: Dict[str, List[Position]] = defaultdict(list)
        for p in positions:
            by_aisle_pos[p.aisle_id].append(p)
        asset_rollups = self._source_asset_repo.summarize_assets_for_aisles(list(aisle_ids))

        rows: List[AisleWithLatestJob] = []
        for a in aisles:
            lj = latest_by_aisle.get(a.id)
            pos_list = by_aisle_pos.get(a.id, [])
            rollup = asset_rollups.get(a.id)
            assets_count = rollup.count if rollup is not None else 0
            asset_last = rollup.last_uploaded_at if rollup is not None else None
            pending = sum(1 for p in pos_list if p.needs_review)
            last_at = _aisle_last_activity_at(a, lj, pos_list, asset_last)
            rows.append(
                AisleWithLatestJob(
                    aisle=a,
                    latest_job=lj,
                    assets_count=assets_count,
                    positions_count=len(pos_list),
                    pending_review_positions_count=pending,
                    last_activity_at=last_at,
                )
            )

        reverse = (q.sort_dir or "asc").strip().lower() == "desc"
        rows.sort(key=lambda r: _row_sort_key(r, q.sort_by), reverse=reverse)
        total = len(rows)
        page = max(1, q.page)
        page_size = max(1, min(q.page_size, 200))
        start = (page - 1) * page_size
        return rows[start : start + page_size], total
