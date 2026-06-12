"""Explicit job-scoped result cleanup — Phase 2 Part 3."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum

from src.application.ports.job_result_unit_of_work import (
    JobResultRepositories,
    JobResultUnitOfWorkFactory,
)
from src.application.ports.repositories import AisleRepository, JobRepository
from src.domain.jobs.entities import JobStatus

logger = logging.getLogger(__name__)

_ACTIVE_STATUSES = frozenset(
    {
        JobStatus.STARTING,
        JobStatus.RUNNING,
        JobStatus.CANCEL_REQUESTED,
    }
)


class CleanupJobResultsOutcome(str, Enum):
    CLEANED = "cleaned"
    NOTHING_TO_CLEAN = "nothing_to_clean"
    REJECTED_OPERATIONAL_JOB = "rejected_operational_job"
    REJECTED_ACTIVE_JOB = "rejected_active_job"
    REJECTED_SCOPE_MISMATCH = "rejected_scope_mismatch"
    REJECTED_JOB_NOT_FOUND = "rejected_job_not_found"
    REJECTED_AISLE_NOT_FOUND = "rejected_aisle_not_found"


@dataclass(frozen=True)
class CleanupJobResultsCommand:
    inventory_id: str
    aisle_id: str
    job_id: str
    reason: str = ""


@dataclass(frozen=True)
class CleanupJobResultsResult:
    outcome: CleanupJobResultsOutcome
    rows_deleted: int = 0


class CleanupJobResultsUseCase:
    def __init__(
        self,
        *,
        aisle_repo: AisleRepository,
        job_repo: JobRepository,
        job_result_uow_factory: JobResultUnitOfWorkFactory,
        repositories: JobResultRepositories,
    ) -> None:
        self._aisle_repo = aisle_repo
        self._job_repo = job_repo
        self._uow_factory = job_result_uow_factory
        self._repositories = repositories

    def execute(self, command: CleanupJobResultsCommand) -> CleanupJobResultsResult:
        aisle = self._aisle_repo.get_by_id(command.aisle_id)
        if aisle is None:
            return CleanupJobResultsResult(outcome=CleanupJobResultsOutcome.REJECTED_AISLE_NOT_FOUND)

        job = self._job_repo.get_by_id(command.job_id)
        if job is None:
            return CleanupJobResultsResult(outcome=CleanupJobResultsOutcome.REJECTED_JOB_NOT_FOUND)
        if job.target_type != "aisle" or job.target_id != command.aisle_id:
            return CleanupJobResultsResult(outcome=CleanupJobResultsOutcome.REJECTED_SCOPE_MISMATCH)
        if aisle.operational_job_id == command.job_id:
            return CleanupJobResultsResult(
                outcome=CleanupJobResultsOutcome.REJECTED_OPERATIONAL_JOB
            )
        if job.status in _ACTIVE_STATUSES:
            return CleanupJobResultsResult(outcome=CleanupJobResultsOutcome.REJECTED_ACTIVE_JOB)

        with self._uow_factory(self._repositories) as uow:
            before = uow.scope_store.count_scope(
                inventory_id=command.inventory_id,
                aisle_id=command.aisle_id,
                job_id=command.job_id,
            )
            total_before = (
                before.positions
                + before.products
                + before.evidence
                + before.raw_labels
                + before.normalized_labels
                + before.final_counts
            )
            if total_before == 0:
                return CleanupJobResultsResult(outcome=CleanupJobResultsOutcome.NOTHING_TO_CLEAN)
            uow.scope_store.delete_scope(
                inventory_id=command.inventory_id,
                aisle_id=command.aisle_id,
                job_id=command.job_id,
            )
            uow.commit()

        logger.info(
            "cleanup_job_results aisle_id=%s job_id=%s reason=%s rows=%d",
            command.aisle_id,
            command.job_id,
            command.reason,
            total_before,
        )
        return CleanupJobResultsResult(
            outcome=CleanupJobResultsOutcome.CLEANED,
            rows_deleted=total_before,
        )
