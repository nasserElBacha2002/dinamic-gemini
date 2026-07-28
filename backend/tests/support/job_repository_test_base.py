"""Shared JobRepository base for tests that do not exercise claim/reclaim."""

from __future__ import annotations

from datetime import datetime

from src.application.ports.repositories import JobRepository
from src.domain.jobs.claim import JobClaimResult, StaleReclaimResult


class JobRepositoryTestBase(JobRepository):
    """Implements Phase-1 claim/reclaim abstract methods as hard failures.

    Suites that need real claim semantics should use ``MemoryJobRepository`` instead.
    """

    def try_claim_starting_to_running(
        self,
        job_id: str,
        *,
        now: datetime,
        claim_owner_id: str,
        aisle_id: str,
        lease_duration_seconds: int = 60,
    ) -> JobClaimResult:
        raise AssertionError(
            f"{type(self).__name__} does not support try_claim_starting_to_running"
        )

    def try_reclaim_stale_job_and_reconcile_aisle(
        self,
        job_id: str,
        *,
        now: datetime,
        stale_after_seconds: int,
    ) -> StaleReclaimResult:
        raise AssertionError(
            f"{type(self).__name__} does not support try_reclaim_stale_job_and_reconcile_aisle"
        )

    def reclaim_stale_running_jobs(
        self, stale_after_seconds: int, *, batch_size: int = 100
    ) -> int:
        return 0
