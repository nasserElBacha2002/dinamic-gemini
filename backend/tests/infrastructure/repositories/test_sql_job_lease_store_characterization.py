"""Characterization: SqlJobRepository delegates lease CAS to SqlJobLeaseStore."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from src.domain.jobs.entities import Job, JobStatus
from src.domain.jobs.lease import JobLease, LeaseWriteOutcome
from src.infrastructure.repositories.sql_job_lease_store import SqlJobLeaseStore
from src.infrastructure.repositories.sql_job_repository import SqlJobRepository


def test_sql_job_repository_exposes_lease_store_collaborator() -> None:
    client = MagicMock()
    repo = SqlJobRepository(client)
    assert isinstance(repo._lease_store, SqlJobLeaseStore)


def test_renew_lease_delegates_to_store() -> None:
    client = MagicMock()
    repo = SqlJobRepository(client)
    now = datetime(2026, 7, 28, 12, 0, 0, tzinfo=timezone.utc)
    lease = JobLease(
        job_id="job-1",
        owner_id="owner-a",
        fencing_token=1,
        acquired_at=now,
        expires_at=now + timedelta(minutes=5),
    )
    expected = MagicMock()
    repo._lease_store.renew_lease = MagicMock(return_value=expected)
    assert repo.renew_lease(lease, now=now, extension_seconds=60) is expected
    repo._lease_store.renew_lease.assert_called_once_with(
        lease, now=now, extension_seconds=60
    )


def test_complete_if_leased_delegates_to_store() -> None:
    client = MagicMock()
    repo = SqlJobRepository(client)
    now = datetime(2026, 7, 28, 12, 0, 0, tzinfo=timezone.utc)
    lease = JobLease(
        job_id="job-1",
        owner_id="owner-a",
        fencing_token=1,
        acquired_at=now,
        expires_at=now + timedelta(minutes=5),
    )
    job = Job(
        id="job-1",
        job_type="process_aisle",
        target_type="aisle",
        target_id="a1",
        status=JobStatus.SUCCEEDED,
        payload_json={},
        created_at=now,
        updated_at=now,
    )
    repo._lease_store.complete_if_leased = MagicMock(
        return_value=MagicMock(outcome=LeaseWriteOutcome.APPLIED)
    )
    repo.complete_if_leased(lease, job, now=now)
    repo._lease_store.complete_if_leased.assert_called_once_with(lease, job, now=now)
