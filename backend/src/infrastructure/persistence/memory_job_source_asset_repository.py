"""In-memory JobSourceAssetRepository for tests and non-SQL modes."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

from src.application.ports.job_source_asset_repository import JobSourceAssetLink


class MemoryJobSourceAssetRepository:
    def __init__(self) -> None:
        self._by_job: dict[str, list[JobSourceAssetLink]] = defaultdict(list)

    def replace_for_job(self, job_id: str, links: Sequence[JobSourceAssetLink]) -> None:
        ordered = sorted(links, key=lambda x: (x.position_order, x.asset_role, x.id))
        self._by_job[job_id] = list(ordered)

    def list_for_job(self, job_id: str) -> list[JobSourceAssetLink]:
        return list(self._by_job.get(job_id, []))
