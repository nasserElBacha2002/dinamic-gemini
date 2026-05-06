"""
GetAisleProcessingStatus use case — v3.0 (Épica 4).

Returns the aisle, latest job, operational pointer, and recent jobs for status / run browsing (Phase 2).
"""

from __future__ import annotations

from dataclasses import dataclass

from src.application.ports.repositories import AisleRepository, JobRepository
from src.application.services.aisle_inventory_scope import require_aisle_scoped_to_inventory
from src.application.services.job_stale_reconciler import JobStaleReconciler
from src.domain.aisle.entities import Aisle
from src.domain.jobs.entities import Job


@dataclass
class AisleProcessingStatusResult:
    """Result of GetAisleProcessingStatusUseCase."""

    aisle: Aisle
    latest_job: Job | None
    recent_jobs: tuple[Job, ...]


class GetAisleProcessingStatusUseCase:
    def __init__(
        self,
        aisle_repo: AisleRepository,
        job_repo: JobRepository,
        stale_reconciler: JobStaleReconciler,
        *,
        recent_jobs_limit: int = 20,
    ) -> None:
        self._aisle_repo = aisle_repo
        self._job_repo = job_repo
        self._stale_reconciler = stale_reconciler
        self._recent_limit = max(1, min(int(recent_jobs_limit), 100))

    def execute(self, inventory_id: str, aisle_id: str) -> AisleProcessingStatusResult:
        aisle = require_aisle_scoped_to_inventory(
            self._aisle_repo,
            inventory_id=inventory_id,
            aisle_id=aisle_id,
            detail_style="strict",
        )

        latest_job = self._stale_reconciler.reconcile(
            self._job_repo.get_latest_by_target("aisle", aisle_id)
        )
        recent = tuple(
            self._job_repo.list_jobs_for_target("aisle", aisle_id, limit=self._recent_limit)
        )
        return AisleProcessingStatusResult(aisle=aisle, latest_job=latest_job, recent_jobs=recent)
