"""In-memory compare-and-set operational promotion — Phase 2 Part 3."""

from __future__ import annotations

import threading
from datetime import datetime

from src.application.ports.operational_job_promotion import (
    OperationalJobPromotionRepository,
    PromotionOutcome,
    PromotionResult,
)
from src.application.ports.repositories import AisleRepository, JobRepository


class MemoryOperationalJobPromotionRepository(OperationalJobPromotionRepository):
    def __init__(
        self,
        *,
        aisle_repo: AisleRepository,
        job_repo: JobRepository,
    ) -> None:
        self._aisle_repo = aisle_repo
        self._job_repo = job_repo
        self._lock = threading.Lock()

    def promote_if_eligible(
        self,
        *,
        aisle_id: str,
        candidate_job_id: str,
        candidate_created_at: object,
    ) -> PromotionResult:
        if not isinstance(candidate_created_at, datetime):
            return PromotionResult(
                outcome=PromotionOutcome.CONFLICT,
                previous_job_id=None,
                operational_job_id=None,
            )
        with self._lock:
            aisle = self._aisle_repo.get_by_id(aisle_id)
            if aisle is None:
                return PromotionResult(
                    outcome=PromotionOutcome.REJECTED_AISLE_NOT_FOUND,
                    previous_job_id=None,
                    operational_job_id=None,
                )
            previous = aisle.operational_job_id
            if previous == candidate_job_id:
                return PromotionResult(
                    outcome=PromotionOutcome.ALREADY_OPERATIONAL,
                    previous_job_id=previous,
                    operational_job_id=previous,
                )
            if previous:
                current = self._job_repo.get_by_id(previous)
                if current is not None and current.created_at > candidate_created_at:
                    return PromotionResult(
                        outcome=PromotionOutcome.REJECTED_STALE,
                        previous_job_id=previous,
                        operational_job_id=previous,
                    )
            aisle.operational_job_id = candidate_job_id
            self._aisle_repo.save(aisle)
            return PromotionResult(
                outcome=PromotionOutcome.PROMOTED,
                previous_job_id=previous,
                operational_job_id=candidate_job_id,
            )
