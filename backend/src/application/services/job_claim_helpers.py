"""Shared helpers for atomic STARTING→RUNNING claim classification."""

from __future__ import annotations

from src.domain.jobs.claim import TERMINAL_JOB_STATUSES, JobClaimOutcome, JobClaimResult
from src.domain.jobs.entities import Job, JobStatus


def classify_claim_after_cas_miss(
    job: Job | None,
    *,
    execution_id: str | None,
) -> JobClaimResult:
    """Map current job row to a claim outcome when the CAS UPDATE affected 0 rows."""
    if job is None:
        return JobClaimResult(outcome=JobClaimOutcome.NOT_FOUND, reason="job_not_found")

    status_value = job.status.value if isinstance(job.status, JobStatus) else str(job.status)
    if status_value in TERMINAL_JOB_STATUSES or job.status in (
        JobStatus.SUCCEEDED,
        JobStatus.FAILED,
        JobStatus.CANCELED,
        JobStatus.TIMED_OUT,
    ):
        return JobClaimResult(
            outcome=JobClaimOutcome.TERMINAL,
            job=job,
            previous_status=status_value,
            reason="job_terminal",
        )

    if job.status == JobStatus.RUNNING:
        if execution_id is None or not job.execution_id or job.execution_id == execution_id:
            return JobClaimResult(
                outcome=JobClaimOutcome.ALREADY_OWNED,
                job=job,
                previous_status=status_value,
                reason="same_execution_already_running",
            )
        return JobClaimResult(
            outcome=JobClaimOutcome.CONFLICT,
            job=job,
            previous_status=status_value,
            reason="owned_by_other_execution",
        )

    if job.status == JobStatus.STARTING:
        # Lost the race to another claim that already moved past STARTING, or concurrent miss.
        return JobClaimResult(
            outcome=JobClaimOutcome.CONFLICT,
            job=job,
            previous_status=status_value,
            reason="claim_race_lost",
        )

    return JobClaimResult(
        outcome=JobClaimOutcome.INVALID_STATUS,
        job=job,
        previous_status=status_value,
        reason=f"status_not_claimable:{status_value}",
    )
