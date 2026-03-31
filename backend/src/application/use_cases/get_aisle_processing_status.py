"""
GetAisleProcessingStatus use case — v3.0 (Épica 4).

Returns the aisle and its latest job (if any) for operational status display.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from src.application.ports.repositories import AisleRepository, JobRepository
from src.application.errors import AisleNotFoundError
from src.application.services.job_stale_reconciler import JobStaleReconciler
from src.domain.aisle.entities import Aisle
from src.domain.jobs.entities import Job


@dataclass
class AisleProcessingStatusResult:
    """Result of GetAisleProcessingStatusUseCase."""
    aisle: Aisle
    latest_job: Optional[Job]


class GetAisleProcessingStatusUseCase:
    def __init__(
        self,
        aisle_repo: AisleRepository,
        job_repo: JobRepository,
        stale_reconciler: JobStaleReconciler,
    ) -> None:
        self._aisle_repo = aisle_repo
        self._job_repo = job_repo
        self._stale_reconciler = stale_reconciler

    def execute(self, inventory_id: str, aisle_id: str) -> AisleProcessingStatusResult:
        aisle = self._aisle_repo.get_by_id(aisle_id)
        if aisle is None:
            raise AisleNotFoundError(f"Aisle not found: {aisle_id}")
        if aisle.inventory_id != inventory_id:
            raise AisleNotFoundError(
                f"Aisle {aisle_id} does not belong to inventory {inventory_id}"
            )

        latest_job = self._stale_reconciler.reconcile(
            self._job_repo.get_latest_by_target("aisle", aisle_id)
        )
        return AisleProcessingStatusResult(aisle=aisle, latest_job=latest_job)
