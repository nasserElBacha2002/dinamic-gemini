"""Shared JobRepository base for tests that do not exercise claim/reclaim."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

from src.application.ports.repositories import JobRepository
from src.domain.jobs.claim import JobClaimResult, StaleReclaimResult
from src.domain.jobs.entities import Job
from src.domain.jobs.lease import (
    JobLease,
    LeaseRenewalResult,
    LeaseWriteResult,
)


class JobRepositoryTestBase(JobRepository):
    """Implements Phase-1/3 claim/lease abstract methods as hard failures.

    Suites that need real claim/lease semantics should use ``MemoryJobRepository`` instead.
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

    def renew_lease(
        self,
        lease: JobLease,
        *,
        now: datetime,
        extension_seconds: int,
    ) -> LeaseRenewalResult:
        raise AssertionError(f"{type(self).__name__} does not support renew_lease")

    def reacquire_expired_lease(
        self,
        job_id: str,
        *,
        now: datetime,
        new_owner_id: str,
        extension_seconds: int,
    ) -> JobClaimResult:
        raise AssertionError(
            f"{type(self).__name__} does not support reacquire_expired_lease"
        )

    def merge_result_json_if_leased(
        self,
        lease: JobLease,
        patch: dict[str, Any],
        *,
        now: datetime,
    ) -> tuple[LeaseWriteResult, Job | None]:
        raise AssertionError(
            f"{type(self).__name__} does not support merge_result_json_if_leased"
        )

    def assert_lease(self, lease: JobLease, *, now: datetime) -> LeaseWriteResult:
        raise AssertionError(f"{type(self).__name__} does not support assert_lease")

    def complete_if_leased(
        self,
        lease: JobLease,
        job: Job,
        *,
        now: datetime,
    ) -> LeaseWriteResult:
        raise AssertionError(f"{type(self).__name__} does not support complete_if_leased")

    def fail_if_leased(
        self,
        lease: JobLease,
        *,
        now: datetime,
        error_message: str,
        failure_code: str = "PROCESSING_FAILED",
    ) -> LeaseWriteResult:
        raise AssertionError(f"{type(self).__name__} does not support fail_if_leased")

    def update_finalization_if_leased(
        self,
        lease: JobLease,
        *,
        now: datetime,
        mutator: Callable[[Job], None],
    ) -> LeaseWriteResult:
        raise AssertionError(
            f"{type(self).__name__} does not support update_finalization_if_leased"
        )

    def acknowledge_cancel_if_leased(
        self,
        lease: JobLease,
        *,
        now: datetime,
        reason: str,
    ) -> LeaseWriteResult:
        raise AssertionError(
            f"{type(self).__name__} does not support acknowledge_cancel_if_leased"
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
