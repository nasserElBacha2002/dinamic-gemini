"""Phase 3 lease fencing — domain value objects (`src.domain.jobs.lease`)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.domain.jobs.lease import (
    JobLease,
    JobLeaseLostError,
    LeaseRenewalOutcome,
    LeaseRenewalResult,
    LeaseWriteOutcome,
    LeaseWriteResult,
)


def _now() -> datetime:
    return datetime(2026, 7, 28, 12, 0, 0, tzinfo=timezone.utc)


def test_job_lease_is_frozen_and_holds_fields():
    lease = JobLease(
        job_id="job-1",
        owner_id="owner-a",
        fencing_token=1,
        acquired_at=_now(),
        expires_at=_now() + timedelta(seconds=60),
    )
    assert lease.job_id == "job-1"
    assert lease.owner_id == "owner-a"
    assert lease.fencing_token == 1
    with pytest.raises(Exception):
        lease.fencing_token = 2  # type: ignore[misc]


def test_lease_renewal_result_renewed_property():
    lease = JobLease(
        job_id="job-1",
        owner_id="owner-a",
        fencing_token=1,
        acquired_at=_now(),
        expires_at=_now() + timedelta(seconds=60),
    )
    renewed = LeaseRenewalResult(outcome=LeaseRenewalOutcome.RENEWED, lease=lease)
    assert renewed.renewed is True

    lost = LeaseRenewalResult(outcome=LeaseRenewalOutcome.LEASE_LOST, reason="owner_mismatch")
    assert lost.renewed is False
    assert lost.lease is None


@pytest.mark.parametrize(
    "outcome,expected",
    [
        (LeaseRenewalOutcome.RENEWED, True),
        (LeaseRenewalOutcome.LEASE_LOST, False),
        (LeaseRenewalOutcome.JOB_TERMINAL, False),
        (LeaseRenewalOutcome.NOT_FOUND, False),
        (LeaseRenewalOutcome.INVALID_STATE, False),
        (LeaseRenewalOutcome.EXPIRED, False),
    ],
)
def test_lease_renewal_outcome_enum_values_are_stable(outcome: LeaseRenewalOutcome, expected: bool):
    result = LeaseRenewalResult(outcome=outcome)
    assert result.renewed is expected


def test_lease_write_result_applied_property():
    applied = LeaseWriteResult(outcome=LeaseWriteOutcome.APPLIED)
    assert applied.applied is True

    for outcome in (
        LeaseWriteOutcome.LEASE_LOST,
        LeaseWriteOutcome.JOB_TERMINAL,
        LeaseWriteOutcome.NOT_FOUND,
        LeaseWriteOutcome.INVALID_STATE,
    ):
        rejected = LeaseWriteResult(outcome=outcome, reason="x")
        assert rejected.applied is False


def test_job_lease_lost_error_carries_context():
    err = JobLeaseLostError(
        "lost it",
        job_id="job-1",
        owner_id="owner-a",
        fencing_token=2,
        reason="owner_or_fencing_token_mismatch",
    )
    assert str(err) == "lost it"
    assert err.job_id == "job-1"
    assert err.owner_id == "owner-a"
    assert err.fencing_token == 2
    assert err.reason == "owner_or_fencing_token_mismatch"


def test_job_lease_lost_error_defaults():
    err = JobLeaseLostError()
    assert str(err) == "Job lease lost"
    assert err.job_id is None
    assert err.owner_id is None
    assert err.fencing_token is None
    assert err.reason is None
