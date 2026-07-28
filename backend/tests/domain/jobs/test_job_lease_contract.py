"""Shared lease contract: null expiry, empty owner, token 0 are invalid."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.application.services.job_lease_helpers import (
    classify_lease_write_after_cas_miss,
    lease_is_currently_valid,
    lease_is_initialized,
)
from src.domain.jobs.entities import Job, JobStatus
from src.domain.jobs.lease import LeaseWriteOutcome
from tests.support.job_repository_test_base import JobRepositoryTestBase


def _now() -> datetime:
    return datetime(2026, 7, 28, 12, 0, 0, tzinfo=timezone.utc)


def _job(**overrides) -> Job:
    t = _now()
    base = dict(
        id="job-1",
        job_type="process_aisle",
        target_type="aisle",
        target_id="aisle-1",
        status=JobStatus.RUNNING,
        payload_json={},
        created_at=t,
        updated_at=t,
        claim_owner_id="owner-a",
        lease_fencing_token=1,
        lease_expires_at=t + timedelta(seconds=60),
        lease_acquired_at=t,
    )
    base.update(overrides)
    return Job(**base)


def test_null_expiry_is_not_initialized():
    job = _job(lease_expires_at=None)
    assert lease_is_initialized(job) is False
    assert (
        lease_is_currently_valid(
            job, owner_id="owner-a", fencing_token=1, now=_now()
        )
        is False
    )


def test_token_zero_is_not_initialized():
    job = _job(lease_fencing_token=0)
    assert lease_is_initialized(job) is False


def test_empty_owner_is_not_initialized():
    job = _job(claim_owner_id="")
    assert lease_is_initialized(job) is False


def test_expired_lease_is_invalid():
    job = _job(lease_expires_at=_now() - timedelta(seconds=1))
    assert lease_is_initialized(job) is True
    assert (
        lease_is_currently_valid(
            job, owner_id="owner-a", fencing_token=1, now=_now()
        )
        is False
    )


def test_current_expiry_is_valid():
    job = _job(lease_expires_at=_now())
    assert (
        lease_is_currently_valid(
            job, owner_id="owner-a", fencing_token=1, now=_now()
        )
        is True
    )


def test_token_mismatch_classified_as_lease_lost():
    job = _job(lease_fencing_token=2)
    result = classify_lease_write_after_cas_miss(
        job, owner_id="owner-a", fencing_token=1, now=_now()
    )
    assert result.outcome == LeaseWriteOutcome.LEASE_LOST


def test_null_expiry_classified_as_not_initialized():
    job = _job(lease_expires_at=None)
    result = classify_lease_write_after_cas_miss(
        job, owner_id="owner-a", fencing_token=1, now=_now()
    )
    assert result.outcome == LeaseWriteOutcome.LEASE_NOT_INITIALIZED


def test_incomplete_adapter_cannot_instantiate():
    with pytest.raises(TypeError):
        JobRepositoryTestBase()  # type: ignore[abstract]
