"""Shared helpers for atomic STARTING→RUNNING claim classification."""

from __future__ import annotations

from src.domain.jobs.claim import TERMINAL_JOB_STATUSES, JobClaimOutcome, JobClaimResult
from src.domain.jobs.entities import Job, JobStatus


def classify_claim_after_cas_miss(
    job: Job | None,
    *,
    claim_owner_id: str | None,
) -> JobClaimResult:
    """Map current job row to a claim outcome when the CAS UPDATE affected 0 rows.

    ``ALREADY_OWNED`` requires both caller and persisted ``claim_owner_id`` non-null and equal.
    Matching ``execution_id`` alone never grants ownership.
    """
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
            claim_owner_id=claim_owner_id,
        )

    if job.status == JobStatus.RUNNING:
        persisted = (job.claim_owner_id or "").strip() or None
        caller = (claim_owner_id or "").strip() or None
        if caller is not None and persisted is not None and caller == persisted:
            return JobClaimResult(
                outcome=JobClaimOutcome.ALREADY_OWNED,
                job=job,
                previous_status=status_value,
                reason="same_claim_owner_already_running",
                claim_owner_id=caller,
            )
        return JobClaimResult(
            outcome=JobClaimOutcome.CONFLICT,
            job=job,
            previous_status=status_value,
            reason="owned_by_other_or_null_claim_owner",
            claim_owner_id=claim_owner_id,
        )

    if job.status == JobStatus.STARTING:
        return JobClaimResult(
            outcome=JobClaimOutcome.CONFLICT,
            job=job,
            previous_status=status_value,
            reason="claim_race_lost",
            claim_owner_id=claim_owner_id,
        )

    return JobClaimResult(
        outcome=JobClaimOutcome.INVALID_STATUS,
        job=job,
        previous_status=status_value,
        reason=f"status_not_claimable:{status_value}",
        claim_owner_id=claim_owner_id,
    )
