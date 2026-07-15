"""DeactivateAisle use case — soft-deactivate an aisle (keeps historical data)."""

from __future__ import annotations

from dataclasses import dataclass

from src.application.errors import ActiveJobExistsError
from src.application.ports.clock import Clock
from src.application.ports.repositories import AisleRepository, JobRepository
from src.application.services.aisle_inventory_scope import require_aisle_scoped_to_inventory
from src.application.services.job_stale_reconciler import JobStaleReconciler
from src.domain.aisle.entities import Aisle
from src.domain.jobs.entities import JobStatus

_DEACTIVATE_BLOCKING_JOB_STATUSES = (
    JobStatus.QUEUED,
    JobStatus.STARTING,
    JobStatus.RUNNING,
    JobStatus.CANCEL_REQUESTED,
)


@dataclass
class DeactivateAisleCommand:
    inventory_id: str
    aisle_id: str


class DeactivateAisleUseCase:
    def __init__(
        self,
        aisle_repo: AisleRepository,
        job_repo: JobRepository,
        clock: Clock,
        stale_reconciler: JobStaleReconciler,
    ) -> None:
        self._aisle_repo = aisle_repo
        self._job_repo = job_repo
        self._clock = clock
        self._stale_reconciler = stale_reconciler

    def execute(self, command: DeactivateAisleCommand) -> Aisle:
        aisle = require_aisle_scoped_to_inventory(
            self._aisle_repo,
            inventory_id=command.inventory_id,
            aisle_id=command.aisle_id,
            detail_style="strict",
        )
        if not aisle.is_active:
            return aisle

        latest = self._stale_reconciler.reconcile(
            self._job_repo.get_latest_by_target("aisle", command.aisle_id)
        )
        if latest is not None and latest.status in _DEACTIVATE_BLOCKING_JOB_STATUSES:
            raise ActiveJobExistsError(
                f"Aisle {command.aisle_id} already has an active job (status={latest.status.value})"
            )

        aisle.deactivate(self._clock.now())
        self._aisle_repo.save(aisle)
        return aisle
