"""Phase 3 lease fencing — MemoryJobRepository semantics.

Mirrors the SQL implementation contract: monotonic fencing token, CAS-based renewal,
stale-write rejection, and expired-lease reacquisition ("stealing").
"""

from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone

from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.jobs.claim import JobClaimOutcome
from src.domain.jobs.entities import Job, JobStatus
from src.domain.jobs.lease import JobLease, LeaseRenewalOutcome, LeaseWriteOutcome
from src.infrastructure.repositories.memory_aisle_repository import MemoryAisleRepository
from src.infrastructure.repositories.memory_job_repository import MemoryJobRepository


def _now() -> datetime:
    return datetime(2026, 7, 28, 12, 0, 0, tzinfo=timezone.utc)


def _job(
    *,
    job_id: str = "job-1",
    status: JobStatus = JobStatus.STARTING,
    aisle_id: str = "aisle-1",
) -> Job:
    t = _now()
    return Job(
        id=job_id,
        job_type="process_aisle",
        target_type="aisle",
        target_id=aisle_id,
        status=status,
        payload_json={"aisle_id": aisle_id},
        created_at=t,
        updated_at=t,
    )


def _aisle(*, status: AisleStatus = AisleStatus.QUEUED, aisle_id: str = "aisle-1") -> Aisle:
    t = _now()
    return Aisle(
        id=aisle_id,
        inventory_id="inv-1",
        code="A1",
        status=status,
        created_at=t,
        updated_at=t,
    )


def _repos() -> tuple[MemoryJobRepository, MemoryAisleRepository]:
    aisle_repo = MemoryAisleRepository()
    job_repo = MemoryJobRepository(aisle_repo=aisle_repo)
    return job_repo, aisle_repo


def _claim(
    job_repo: MemoryJobRepository,
    *,
    job_id: str = "job-1",
    owner: str = "owner-a",
    aisle_id: str = "aisle-1",
    now: datetime | None = None,
    lease_duration_seconds: int = 60,
):
    return job_repo.try_claim_starting_to_running(
        job_id,
        now=now or _now(),
        claim_owner_id=owner,
        aisle_id=aisle_id,
        lease_duration_seconds=lease_duration_seconds,
    )


def test_first_acquire_grants_fencing_token_one():
    job_repo, aisle_repo = _repos()
    job_repo.save(_job())
    aisle_repo.save(_aisle())

    result = _claim(job_repo)

    assert result.outcome == JobClaimOutcome.ACQUIRED
    assert result.lease is not None
    assert result.lease.fencing_token == 1
    assert result.lease.owner_id == "owner-a"
    assert result.job is not None
    assert result.job.lease_fencing_token == 1
    assert result.job.lease_expires_at == _now() + timedelta(seconds=60)


def test_renew_ok_extends_expiry_without_incrementing_token():
    job_repo, aisle_repo = _repos()
    job_repo.save(_job())
    aisle_repo.save(_aisle())
    lease = _claim(job_repo).lease
    assert lease is not None

    later = _now() + timedelta(seconds=30)
    result = job_repo.renew_lease(lease, now=later, extension_seconds=60)

    assert result.outcome == LeaseRenewalOutcome.RENEWED
    assert result.renewed is True
    assert result.lease is not None
    assert result.lease.fencing_token == lease.fencing_token
    assert result.lease.expires_at == later + timedelta(seconds=60)
    persisted = job_repo.get_by_id("job-1")
    assert persisted is not None
    assert persisted.lease_fencing_token == 1
    assert persisted.lease_expires_at == later + timedelta(seconds=60)


def test_renew_wrong_owner_returns_lease_lost():
    job_repo, aisle_repo = _repos()
    job_repo.save(_job())
    aisle_repo.save(_aisle())
    lease = _claim(job_repo).lease
    assert lease is not None

    impostor_lease = JobLease(
        job_id=lease.job_id,
        owner_id="owner-b",
        fencing_token=lease.fencing_token,
        acquired_at=lease.acquired_at,
        expires_at=lease.expires_at,
    )
    result = job_repo.renew_lease(impostor_lease, now=_now(), extension_seconds=60)

    assert result.outcome == LeaseRenewalOutcome.LEASE_LOST
    assert result.renewed is False
    # Original owner's lease is untouched.
    persisted = job_repo.get_by_id("job-1")
    assert persisted is not None
    assert persisted.claim_owner_id == "owner-a"


def test_renew_after_expiry_returns_expired():
    job_repo, aisle_repo = _repos()
    job_repo.save(_job())
    aisle_repo.save(_aisle())
    lease = _claim(job_repo, lease_duration_seconds=60).lease
    assert lease is not None

    after_expiry = _now() + timedelta(seconds=120)
    result = job_repo.renew_lease(lease, now=after_expiry, extension_seconds=60)

    assert result.outcome == LeaseRenewalOutcome.EXPIRED
    assert result.renewed is False


def test_reacquire_expired_lease_increments_fencing_token():
    job_repo, aisle_repo = _repos()
    job_repo.save(_job())
    aisle_repo.save(_aisle())
    first = _claim(job_repo, owner="owner-a", lease_duration_seconds=60)
    assert first.lease is not None
    assert first.lease.fencing_token == 1

    after_expiry = _now() + timedelta(seconds=120)
    stolen = job_repo.reacquire_expired_lease(
        "job-1", now=after_expiry, new_owner_id="owner-b", extension_seconds=60
    )

    assert stolen.outcome == JobClaimOutcome.ACQUIRED
    assert stolen.lease is not None
    assert stolen.lease.fencing_token == 2
    assert stolen.lease.owner_id == "owner-b"
    persisted = job_repo.get_by_id("job-1")
    assert persisted is not None
    assert persisted.claim_owner_id == "owner-b"
    assert persisted.lease_fencing_token == 2

    # The original (now stolen) lease can no longer renew.
    original_lease = first.lease
    stale_renew = job_repo.renew_lease(original_lease, now=after_expiry, extension_seconds=60)
    assert stale_renew.outcome == LeaseRenewalOutcome.LEASE_LOST


def test_reacquire_not_expired_returns_conflict():
    job_repo, aisle_repo = _repos()
    job_repo.save(_job())
    aisle_repo.save(_aisle())
    _claim(job_repo, owner="owner-a", lease_duration_seconds=60)

    still_active = _now() + timedelta(seconds=10)
    result = job_repo.reacquire_expired_lease(
        "job-1", now=still_active, new_owner_id="owner-b", extension_seconds=60
    )

    assert result.outcome == JobClaimOutcome.CONFLICT
    persisted = job_repo.get_by_id("job-1")
    assert persisted is not None
    assert persisted.claim_owner_id == "owner-a"


def test_stale_merge_rejected_after_lease_stolen():
    job_repo, aisle_repo = _repos()
    job_repo.save(_job())
    aisle_repo.save(_aisle())
    first = _claim(job_repo, owner="owner-a", lease_duration_seconds=60)
    assert first.lease is not None

    after_expiry = _now() + timedelta(seconds=120)
    job_repo.reacquire_expired_lease(
        "job-1", now=after_expiry, new_owner_id="owner-b", extension_seconds=60
    )

    outcome, job = job_repo.merge_result_json_if_leased(
        first.lease, {"stale_key": "should_not_apply"}, now=after_expiry
    )

    assert outcome.outcome == LeaseWriteOutcome.LEASE_LOST
    assert outcome.applied is False
    assert job is not None
    assert "stale_key" not in (job.result_json or {})


def test_current_owner_merge_ok():
    job_repo, aisle_repo = _repos()
    job_repo.save(_job())
    aisle_repo.save(_aisle())
    lease = _claim(job_repo, owner="owner-a", lease_duration_seconds=60).lease
    assert lease is not None

    later = _now() + timedelta(seconds=10)
    outcome, job = job_repo.merge_result_json_if_leased(
        lease, {"progress": {"done": 1}}, now=later
    )

    assert outcome.outcome == LeaseWriteOutcome.APPLIED
    assert outcome.applied is True
    assert job is not None
    assert job.result_json == {"progress": {"done": 1}}

    # A sibling key merged separately is preserved (no clobber).
    outcome2, job2 = job_repo.merge_result_json_if_leased(
        lease, {"other": "value"}, now=later
    )
    assert outcome2.applied is True
    assert job2 is not None
    assert job2.result_json == {"progress": {"done": 1}, "other": "value"}


def test_concurrent_style_sequential_steal_chain():
    """Simulate two workers racing across expiries: each steal bumps the token by 1."""
    job_repo, aisle_repo = _repos()
    job_repo.save(_job())
    aisle_repo.save(_aisle())

    lease_a = _claim(job_repo, owner="owner-a", lease_duration_seconds=30).lease
    assert lease_a is not None
    assert lease_a.fencing_token == 1

    t1 = _now() + timedelta(seconds=31)
    steal_b = job_repo.reacquire_expired_lease(
        "job-1", now=t1, new_owner_id="owner-b", extension_seconds=30
    )
    assert steal_b.lease is not None
    assert steal_b.lease.fencing_token == 2

    t2 = t1 + timedelta(seconds=31)
    steal_c = job_repo.reacquire_expired_lease(
        "job-1", now=t2, new_owner_id="owner-c", extension_seconds=30
    )
    assert steal_c.lease is not None
    assert steal_c.lease.fencing_token == 3

    # Owner A's (stale) lease can neither renew nor write.
    stale_renew = job_repo.renew_lease(lease_a, now=t2, extension_seconds=30)
    assert stale_renew.outcome == LeaseRenewalOutcome.LEASE_LOST

    # Owner B's lease is also now stale (superseded by C).
    stale_write, _ = job_repo.merge_result_json_if_leased(
        steal_b.lease, {"x": 1}, now=t2
    )
    assert stale_write.outcome == LeaseWriteOutcome.LEASE_LOST

    # Owner C (current) can renew and write successfully.
    current_renew = job_repo.renew_lease(steal_c.lease, now=t2, extension_seconds=30)
    assert current_renew.outcome == LeaseRenewalOutcome.RENEWED

    current_write, job = job_repo.merge_result_json_if_leased(
        steal_c.lease, {"final": True}, now=t2
    )
    assert current_write.applied is True
    assert job is not None
    assert job.result_json == {"final": True}


def test_touch_heartbeat_if_leased_delegates_to_renew():
    job_repo, aisle_repo = _repos()
    job_repo.save(_job())
    aisle_repo.save(_aisle())
    lease = _claim(job_repo, lease_duration_seconds=60).lease
    assert lease is not None

    later = _now() + timedelta(seconds=10)
    result = job_repo.touch_heartbeat_if_leased(lease, now=later, extension_seconds=60)

    assert result.outcome == LeaseRenewalOutcome.RENEWED
    persisted = job_repo.get_by_id("job-1")
    assert persisted is not None
    assert persisted.last_heartbeat_at == later


def test_complete_if_leased_rejects_stale_token():
    job_repo, aisle_repo = _repos()
    job_repo.save(_job())
    aisle_repo.save(_aisle())
    first = _claim(job_repo, owner="owner-a", lease_duration_seconds=60)
    lease_a = first.lease
    assert lease_a is not None

    after = _now() + timedelta(seconds=61)
    stolen = job_repo.reacquire_expired_lease(
        "job-1", now=after, new_owner_id="owner-b", extension_seconds=60
    )
    assert stolen.lease is not None

    job = job_repo.get_by_id("job-1")
    assert job is not None
    stale_payload = copy.copy(job)
    stale_payload.status = JobStatus.SUCCEEDED
    stale_payload.result_json = {"ok": True}
    stale = job_repo.complete_if_leased(lease_a, stale_payload, now=after)
    assert stale.outcome == LeaseWriteOutcome.LEASE_LOST

    current_job = job_repo.get_by_id("job-1")
    assert current_job is not None
    ok_payload = copy.copy(current_job)
    ok_payload.status = JobStatus.SUCCEEDED
    ok_payload.result_json = {"ok": True}
    ok = job_repo.complete_if_leased(stolen.lease, ok_payload, now=after)
    assert ok.applied is True
    persisted = job_repo.get_by_id("job-1")
    assert persisted is not None
    assert persisted.status == JobStatus.SUCCEEDED


def test_fail_if_leased_rejects_stale_owner():
    job_repo, aisle_repo = _repos()
    job_repo.save(_job())
    aisle_repo.save(_aisle())
    first = _claim(job_repo, owner="owner-a", lease_duration_seconds=60)
    lease_a = first.lease
    assert lease_a is not None

    after = _now() + timedelta(seconds=61)
    stolen = job_repo.reacquire_expired_lease(
        "job-1", now=after, new_owner_id="owner-b", extension_seconds=60
    )
    assert stolen.lease is not None

    stale = job_repo.fail_if_leased(
        lease_a, now=after, error_message="stale fail", failure_code="X"
    )
    assert stale.outcome == LeaseWriteOutcome.LEASE_LOST
    persisted = job_repo.get_by_id("job-1")
    assert persisted is not None
    assert persisted.status == JobStatus.RUNNING

    ok = job_repo.fail_if_leased(
        stolen.lease, now=after, error_message="real fail", failure_code="Y"
    )
    assert ok.applied is True
    persisted = job_repo.get_by_id("job-1")
    assert persisted is not None
    assert persisted.status == JobStatus.FAILED
    assert persisted.failure_code == "Y"


def test_assert_lease_and_finalization_race_memory():
    job_repo, aisle_repo = _repos()
    job_repo.save(_job())
    aisle_repo.save(_aisle())
    lease_a = _claim(job_repo, owner="owner-a", lease_duration_seconds=30).lease
    assert lease_a is not None
    t = _now() + timedelta(seconds=31)
    lease_b = job_repo.reacquire_expired_lease(
        "job-1", now=t, new_owner_id="owner-b", extension_seconds=30
    ).lease
    assert lease_b is not None

    assert job_repo.assert_lease(lease_a, now=t).outcome == LeaseWriteOutcome.LEASE_LOST
    assert job_repo.assert_lease(lease_b, now=t).applied is True

    job = job_repo.get_by_id("job-1")
    assert job is not None
    stale_payload = copy.copy(job)
    stale_payload.status = JobStatus.SUCCEEDED
    stale_complete = job_repo.complete_if_leased(lease_a, stale_payload, now=t)
    assert stale_complete.outcome == LeaseWriteOutcome.LEASE_LOST
    current = job_repo.get_by_id("job-1")
    assert current is not None
    ok_payload = copy.copy(current)
    ok_payload.status = JobStatus.SUCCEEDED
    assert job_repo.complete_if_leased(lease_b, ok_payload, now=t).applied is True
