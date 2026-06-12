"""Validates and promotes operational job pointers — Phase 2 Part 3."""

from __future__ import annotations

import logging

from src.application.ports.operational_job_promotion import (
    OperationalJobPromotionRepository,
    PromotionOutcome,
    PromotionResult,
)
from src.application.ports.repositories import AisleRepository, JobRepository
from src.domain.jobs.entities import JobStatus

logger = logging.getLogger(__name__)

_PROCESS_AISLE = "process_aisle"
_AISLE_TARGET = "aisle"


class OperationalResultPromotionService:
    """Validate eligibility and delegate atomic promotion. Does not mutate job status."""

    def __init__(
        self,
        *,
        aisle_repo: AisleRepository,
        job_repo: JobRepository,
        promotion_repo: OperationalJobPromotionRepository,
    ) -> None:
        self._aisle_repo = aisle_repo
        self._job_repo = job_repo
        self._promotion_repo = promotion_repo

    def promote_for_success(self, *, aisle_id: str, candidate_job_id: str) -> PromotionResult:
        aisle = self._aisle_repo.get_by_id(aisle_id)
        if aisle is None:
            return PromotionResult(
                outcome=PromotionOutcome.REJECTED_AISLE_NOT_FOUND,
                previous_job_id=None,
                operational_job_id=None,
            )

        job = self._job_repo.get_by_id(candidate_job_id)
        if job is None:
            return PromotionResult(
                outcome=PromotionOutcome.REJECTED_JOB_NOT_FOUND,
                previous_job_id=aisle.operational_job_id,
                operational_job_id=aisle.operational_job_id,
            )
        if job.target_type != _AISLE_TARGET or job.target_id != aisle_id:
            return PromotionResult(
                outcome=PromotionOutcome.REJECTED_WRONG_AISLE,
                previous_job_id=aisle.operational_job_id,
                operational_job_id=aisle.operational_job_id,
            )
        if job.job_type != _PROCESS_AISLE:
            return PromotionResult(
                outcome=PromotionOutcome.REJECTED_INVALID_JOB_TYPE,
                previous_job_id=aisle.operational_job_id,
                operational_job_id=aisle.operational_job_id,
            )
        if job.status != JobStatus.SUCCEEDED:
            return PromotionResult(
                outcome=PromotionOutcome.REJECTED_INVALID_STATUS,
                previous_job_id=aisle.operational_job_id,
                operational_job_id=aisle.operational_job_id,
            )

        previous = aisle.operational_job_id
        result = self._promotion_repo.promote_if_eligible(
            aisle_id=aisle_id,
            candidate_job_id=candidate_job_id,
            candidate_created_at=job.created_at,
        )
        logger.info(
            "operational_promotion aisle_id=%s candidate=%s outcome=%s previous=%s operational=%s",
            aisle_id,
            candidate_job_id,
            result.outcome.value,
            previous,
            result.operational_job_id,
        )
        return result

    def is_stale_non_operational_failure(self, *, aisle_id: str, failing_job_id: str) -> bool:
        """True when a newer succeeded operational job should block aisle downgrade."""
        aisle = self._aisle_repo.get_by_id(aisle_id)
        if aisle is None:
            return False
        op_id = aisle.operational_job_id
        if not op_id or op_id == failing_job_id:
            return False
        op_job = self._job_repo.get_by_id(op_id)
        failing_job = self._job_repo.get_by_id(failing_job_id)
        if op_job is None or failing_job is None:
            return False
        if op_job.status != JobStatus.SUCCEEDED:
            return False
        return op_job.created_at >= failing_job.created_at
