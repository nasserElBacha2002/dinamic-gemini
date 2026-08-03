"""Aisle-scoped processing recovery (transactional orchestration over job recovery)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

from src.application.ports.clock import Clock
from src.application.ports.repositories import AisleRepository, JobRepository
from src.application.services.aisle_processing_state import (
    AisleProcessingStateView,
    resolve_aisle_processing_state,
)
from src.application.use_cases.aisles.cancel_aisle_job import (
    CancelAisleJobCommand,
    CancelAisleJobUseCase,
)
from src.application.use_cases.aisles.get_aisle_processing_status import (
    GetAisleProcessingStatusUseCase,
)
from src.application.use_cases.recovery.recover_stale_job import (
    RecoverStaleJobCommand,
    RecoverStaleJobOutcome,
    RecoverStaleJobUseCase,
)
from src.domain.jobs.entities import Job, JobStatus
from src.observability.logging import log_event

logger = logging.getLogger(__name__)


class RecoverAisleProcessingOutcome(str, Enum):
    NO_ACTION = "NO_ACTION"
    JOB_ALIVE = "JOB_ALIVE"
    RECOVERED = "RECOVERED"
    RELAUNCHED = "RELAUNCHED"
    ORPHAN_CANCELED = "ORPHAN_CANCELED"
    FAILED = "FAILED"
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"


@dataclass(frozen=True, slots=True)
class RecoverAisleProcessingCommand:
    inventory_id: str
    aisle_id: str
    actor: str
    reason: str = "client_recover"
    dry_run: bool = False
    stale_after_seconds: int = 900


@dataclass(frozen=True, slots=True)
class RecoverAisleProcessingResult:
    outcome: RecoverAisleProcessingOutcome
    processing_state: AisleProcessingStateView
    job_id: str | None = None
    new_job_id: str | None = None
    detail: str | None = None


def _status_snapshot(
    *,
    status_uc: GetAisleProcessingStatusUseCase,
    inventory_id: str,
    aisle_id: str,
    clock: Clock,
    stale_after_seconds: int,
) -> tuple[Any, AisleProcessingStateView]:
    status = status_uc.execute(inventory_id, aisle_id)
    view = resolve_aisle_processing_state(
        latest_job=status.latest_job,
        recent_jobs=status.recent_jobs,
        operational_job_id=getattr(status.aisle, "operational_job_id", None),
        stale_after_seconds=stale_after_seconds,
        clock=clock,
    )
    return status, view


@dataclass
class RecoverAisleProcessingUseCase:
    """Recover aisle processing using lease/heartbeat evidence (not age alone)."""

    status_use_case: GetAisleProcessingStatusUseCase
    recover_stale: RecoverStaleJobUseCase
    cancel_job: CancelAisleJobUseCase
    aisle_repo: AisleRepository
    job_repo: JobRepository
    clock: Clock

    def execute(self, command: RecoverAisleProcessingCommand) -> RecoverAisleProcessingResult:
        try:
            status, view = _status_snapshot(
                status_uc=self.status_use_case,
                inventory_id=command.inventory_id,
                aisle_id=command.aisle_id,
                clock=self.clock,
                stale_after_seconds=command.stale_after_seconds,
            )
        except Exception:
            raise

        log_event(
            "aisle_processing_recover_started",
            component="recovery",
            operation="recover_aisle_processing",
            inventory_id=command.inventory_id,
            aisle_id=command.aisle_id,
            actor=command.actor,
            state=view.state,
            job_id=view.job_id,
            dry_run=command.dry_run,
        )

        if view.state in {"IDLE", "COMPLETED", "FAILED"}:
            return RecoverAisleProcessingResult(
                outcome=RecoverAisleProcessingOutcome.NO_ACTION,
                processing_state=view,
                job_id=view.job_id,
                detail="nothing_to_recover",
            )

        if view.state in {"RUNNING", "STARTING", "SUSPECTED_STALE"} and not view.recoverable:
            return RecoverAisleProcessingResult(
                outcome=RecoverAisleProcessingOutcome.JOB_ALIVE,
                processing_state=view,
                job_id=view.job_id,
                detail="job_has_live_evidence",
            )

        if not view.job_id:
            return RecoverAisleProcessingResult(
                outcome=RecoverAisleProcessingOutcome.NO_ACTION,
                processing_state=view,
                detail="missing_job_id",
            )

        job = self.job_repo.get_by_id(view.job_id)
        if job is None:
            return RecoverAisleProcessingResult(
                outcome=RecoverAisleProcessingOutcome.NOT_FOUND,
                processing_state=view,
                job_id=view.job_id,
                detail="job_not_found",
            )

        if command.dry_run:
            return RecoverAisleProcessingResult(
                outcome=RecoverAisleProcessingOutcome.NO_ACTION,
                processing_state=view,
                job_id=view.job_id,
                detail="dry_run",
            )

        # QUEUED orphan without worker claim → cancel and free aisle.
        if job.status is JobStatus.QUEUED and not (job.claim_owner_id or "").strip():
            return self._cancel_orphan(command=command, job=job, prior_view=view)

        # Prefer lease-aware stale recovery (reclaim + optional relaunch).
        stale_result = self.recover_stale.execute(
            RecoverStaleJobCommand(
                job_id=job.id,
                actor=command.actor,
                reason=command.reason,
                dry_run=False,
                stale_after_seconds=command.stale_after_seconds,
            )
        )

        if stale_result.outcome is RecoverStaleJobOutcome.ACTIVE_LEASE:
            _, refreshed = _status_snapshot(
                status_uc=self.status_use_case,
                inventory_id=command.inventory_id,
                aisle_id=command.aisle_id,
                clock=self.clock,
                stale_after_seconds=command.stale_after_seconds,
            )
            return RecoverAisleProcessingResult(
                outcome=RecoverAisleProcessingOutcome.JOB_ALIVE,
                processing_state=refreshed,
                job_id=job.id,
                detail="active_lease",
            )

        if stale_result.outcome in {
            RecoverStaleJobOutcome.RECOVERED,
            RecoverStaleJobOutcome.RELAUNCHED,
            RecoverStaleJobOutcome.ALREADY_RECOVERED,
        }:
            self._clear_operational_if_points_to(command.aisle_id, job.id)
            _, refreshed = _status_snapshot(
                status_uc=self.status_use_case,
                inventory_id=command.inventory_id,
                aisle_id=command.aisle_id,
                clock=self.clock,
                stale_after_seconds=command.stale_after_seconds,
            )
            outcome = (
                RecoverAisleProcessingOutcome.RELAUNCHED
                if stale_result.new_job_id
                else RecoverAisleProcessingOutcome.RECOVERED
            )
            return RecoverAisleProcessingResult(
                outcome=outcome,
                processing_state=refreshed,
                job_id=job.id,
                new_job_id=stale_result.new_job_id,
                detail=stale_result.outcome.value,
            )

        if stale_result.outcome is RecoverStaleJobOutcome.NOT_STALE:
            # STARTING/QUEUED orphan that reclaim refused — cancel if still recoverable.
            if view.recoverable and job.status in {JobStatus.QUEUED, JobStatus.STARTING}:
                return self._cancel_orphan(command=command, job=job, prior_view=view)
            _, refreshed = _status_snapshot(
                status_uc=self.status_use_case,
                inventory_id=command.inventory_id,
                aisle_id=command.aisle_id,
                clock=self.clock,
                stale_after_seconds=command.stale_after_seconds,
            )
            return RecoverAisleProcessingResult(
                outcome=RecoverAisleProcessingOutcome.JOB_ALIVE,
                processing_state=refreshed,
                job_id=job.id,
                detail="not_stale",
            )

        if stale_result.outcome is RecoverStaleJobOutcome.LOST_CAS:
            _, refreshed = _status_snapshot(
                status_uc=self.status_use_case,
                inventory_id=command.inventory_id,
                aisle_id=command.aisle_id,
                clock=self.clock,
                stale_after_seconds=command.stale_after_seconds,
            )
            return RecoverAisleProcessingResult(
                outcome=RecoverAisleProcessingOutcome.CONFLICT,
                processing_state=refreshed,
                job_id=job.id,
                detail="lost_cas",
            )

        _, refreshed = _status_snapshot(
            status_uc=self.status_use_case,
            inventory_id=command.inventory_id,
            aisle_id=command.aisle_id,
            clock=self.clock,
            stale_after_seconds=command.stale_after_seconds,
        )
        return RecoverAisleProcessingResult(
            outcome=RecoverAisleProcessingOutcome.FAILED,
            processing_state=refreshed,
            job_id=job.id,
            detail=stale_result.outcome.value,
        )

    def _cancel_orphan(
        self,
        *,
        command: RecoverAisleProcessingCommand,
        job: Job,
        prior_view: AisleProcessingStateView,
    ) -> RecoverAisleProcessingResult:
        try:
            self.cancel_job.execute(
                CancelAisleJobCommand(
                    inventory_id=command.inventory_id,
                    aisle_id=command.aisle_id,
                    job_id=job.id,
                )
            )
        except Exception as exc:
            logger.warning(
                "recover_aisle_processing cancel failed job_id=%s err=%s",
                job.id,
                exc,
            )
            return RecoverAisleProcessingResult(
                outcome=RecoverAisleProcessingOutcome.FAILED,
                processing_state=prior_view,
                job_id=job.id,
                detail=f"cancel_failed:{type(exc).__name__}",
            )
        self._clear_operational_if_points_to(command.aisle_id, job.id)
        _, refreshed = _status_snapshot(
            status_uc=self.status_use_case,
            inventory_id=command.inventory_id,
            aisle_id=command.aisle_id,
            clock=self.clock,
            stale_after_seconds=command.stale_after_seconds,
        )
        return RecoverAisleProcessingResult(
            outcome=RecoverAisleProcessingOutcome.ORPHAN_CANCELED,
            processing_state=refreshed,
            job_id=job.id,
            detail="orphan_canceled",
        )

    def _clear_operational_if_points_to(self, aisle_id: str, job_id: str) -> None:
        aisle = self.aisle_repo.get_by_id(aisle_id)
        if aisle is None:
            return
        if getattr(aisle, "operational_job_id", None) != job_id:
            return
        aisle.operational_job_id = None
        aisle.updated_at = self.clock.now()
        self.aisle_repo.save(aisle)
