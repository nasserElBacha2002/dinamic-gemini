"""
ListAislesWithStatus use case — v3.0 (Épica 4 correction).

Returns aisles for an inventory with latest job per aisle in one batch.
Uses JobRepository.get_latest_by_targets to avoid N+1 in the API layer.

Sprint 1.3: adds per-aisle rollups (assets, positions, pending review, last_activity_at)
for the Inventory Detail aisle table without N+1 asset list calls.

``last_activity_at`` (per row) is a **list/table freshness** signal for operators: the maximum
timestamp among the aisle row, the **latest job only** (not the full job history), all
positions in that aisle, and the latest asset upload time from ``summarize_assets_for_aisles``.
It is **not** an audit log, a full activity stream, or a dedicated “last human review”
timestamp (unless a review happened to update the newest underlying timestamp).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Sequence

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
    """Compute list freshness: max of aisle times, **latest job** times only, position times, asset rollup."""
    parts: List[datetime] = [aisle.updated_at, aisle.created_at]
    if latest_job is not None:
        parts.extend([latest_job.updated_at, latest_job.created_at])
    for p in positions:
        parts.extend([p.updated_at, p.created_at])
    if asset_last_upload is not None:
        parts.append(asset_last_upload)
    return max(parts)


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

    def execute(self, inventory_id: str) -> List[AisleWithLatestJob]:
        if self._inventory_repo.get_by_id(inventory_id) is None:
            raise InventoryNotFoundError(f"Inventory not found: {inventory_id}")
        aisles = self._aisle_repo.list_by_inventory(inventory_id)
        if not aisles:
            return []
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
        return rows
