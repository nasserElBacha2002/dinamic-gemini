"""Port for unique manual coverage rows: one manual position per (job_id, source_asset_id)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class ManualImageCoverageLink:
    id: str
    job_id: str
    job_source_asset_id: str
    source_asset_id: str
    position_id: str
    aisle_id: str
    inventory_id: str
    created_by_user_id: str | None
    created_at: datetime


class ManualImageCoverageRepository(Protocol):
    def get_by_job_and_asset(
        self, job_id: str, source_asset_id: str
    ) -> ManualImageCoverageLink | None: ...

    def save(self, link: ManualImageCoverageLink) -> None:
        """Persist coverage. Must raise ManualResultAlreadyExistsError on unique violation."""
        ...

    def list_by_job(self, job_id: str) -> list[ManualImageCoverageLink]: ...

    def delete_by_job_and_asset(self, job_id: str, source_asset_id: str) -> None:
        """Remove coverage link (logical invalidate). No-op if missing."""
        ...
