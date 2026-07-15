"""Tests for DeactivateAisleUseCase and ActivateAisleUseCase."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone

import pytest

from src.application.errors import ActiveJobExistsError
from src.application.ports.repositories import AisleRepository, JobRepository
from src.application.services.job_stale_reconciler import JobStaleReconciler
from src.application.use_cases.aisles.activate_aisle import (
    ActivateAisleCommand,
    ActivateAisleUseCase,
)
from src.application.use_cases.aisles.deactivate_aisle import (
    DeactivateAisleCommand,
    DeactivateAisleUseCase,
)
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.jobs.entities import Job, JobStatus


class FixedClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


class StubAisleRepo(AisleRepository):
    def __init__(self) -> None:
        self._store: dict[str, Aisle] = {}
        self.save_calls = 0

    def save(self, aisle: Aisle) -> None:
        self.save_calls += 1
        self._store[aisle.id] = aisle

    def get_by_id(self, aisle_id: str) -> Aisle | None:
        return self._store.get(aisle_id)

    def list_by_inventory(self, inventory_id: str) -> Sequence[Aisle]:
        return [a for a in self._store.values() if a.inventory_id == inventory_id]

    def get_by_inventory_and_code(self, inventory_id: str, code: str) -> Aisle | None:
        for a in self._store.values():
            if a.inventory_id == inventory_id and a.code == code.strip():
                return a
        return None


class StubJobRepo(JobRepository):
    def __init__(self) -> None:
        self._store: dict[str, Job] = {}

    def save(self, job: Job) -> None:
        self._store[job.id] = job

    def get_by_id(self, job_id: str) -> Job | None:
        return self._store.get(job_id)

    def get_latest_by_target(self, target_type: str, target_id: str) -> Job | None:
        candidates = [
            j
            for j in self._store.values()
            if j.target_type == target_type and j.target_id == target_id
        ]
        if not candidates:
            return None
        candidates.sort(key=lambda j: (j.updated_at, j.created_at), reverse=True)
        return candidates[0]

    def get_latest_by_targets(
        self, target_type: str, target_ids: Sequence[str]
    ) -> dict[str, Job]:
        out: dict[str, Job] = {}
        for tid in target_ids:
            latest = self.get_latest_by_target(target_type, tid)
            if latest is not None:
                out[tid] = latest
        return out

    def list_jobs_for_target(
        self, target_type: str, target_id: str, *, limit: int = 50
    ) -> Sequence[Job]:
        rows = [
            j
            for j in self._store.values()
            if j.target_type == target_type and j.target_id == target_id
        ]
        rows.sort(key=lambda j: (j.updated_at, j.created_at), reverse=True)
        return rows[:limit]


def _aisle(now: datetime, *, is_active: bool = True, code: str = "A01") -> Aisle:
    return Aisle(
        id="a1",
        inventory_id="inv-1",
        code=code,
        status=AisleStatus.CREATED,
        created_at=now,
        updated_at=now,
        is_active=is_active,
    )


def _deactivate_uc(
    aisle_repo: StubAisleRepo,
    job_repo: StubJobRepo,
    clock: FixedClock,
) -> DeactivateAisleUseCase:
    return DeactivateAisleUseCase(
        aisle_repo=aisle_repo,
        job_repo=job_repo,
        clock=clock,
        stale_reconciler=JobStaleReconciler(
            job_repo=job_repo,
            clock=clock,
            stale_after_seconds=0,
            aisle_repo=aisle_repo,
        ),
    )


def test_deactivate_aisle_success() -> None:
    created = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    now = datetime(2025, 3, 7, 8, 0, 0, tzinfo=timezone.utc)
    aisle_repo = StubAisleRepo()
    aisle_repo.save(_aisle(created, code="ZONE-9"))
    aisle_repo.save_calls = 0
    job_repo = StubJobRepo()
    uc = _deactivate_uc(aisle_repo, job_repo, FixedClock(now))

    result = uc.execute(DeactivateAisleCommand(inventory_id="inv-1", aisle_id="a1"))

    assert result.is_active is False
    assert result.code == "ZONE-9"
    assert result.updated_at == now
    assert aisle_repo.save_calls == 1


def test_deactivate_aisle_blocks_active_job() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    aisle_repo = StubAisleRepo()
    aisle_repo.save(_aisle(now))
    aisle_repo.save_calls = 0
    job_repo = StubJobRepo()
    job_repo.save(
        Job(
            id="j1",
            target_type="aisle",
            target_id="a1",
            job_type="process_aisle",
            status=JobStatus.RUNNING,
            payload_json={},
            created_at=now,
            updated_at=now,
        )
    )
    uc = _deactivate_uc(aisle_repo, job_repo, FixedClock(now))

    with pytest.raises(ActiveJobExistsError):
        uc.execute(DeactivateAisleCommand(inventory_id="inv-1", aisle_id="a1"))
    assert aisle_repo.save_calls == 0
    assert aisle_repo.get_by_id("a1") is not None
    assert aisle_repo.get_by_id("a1").is_active is True


def test_deactivate_aisle_noop_when_already_inactive() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    later = datetime(2025, 3, 8, 1, 0, 0, tzinfo=timezone.utc)
    aisle_repo = StubAisleRepo()
    aisle_repo.save(_aisle(now, is_active=False, code="KEEP"))
    aisle_repo.save_calls = 0
    uc = _deactivate_uc(aisle_repo, StubJobRepo(), FixedClock(later))

    result = uc.execute(DeactivateAisleCommand(inventory_id="inv-1", aisle_id="a1"))

    assert result.is_active is False
    assert result.code == "KEEP"
    assert result.updated_at == now
    assert aisle_repo.save_calls == 0


def test_activate_aisle_reactivates() -> None:
    created = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    now = datetime(2025, 3, 7, 8, 0, 0, tzinfo=timezone.utc)
    aisle_repo = StubAisleRepo()
    aisle_repo.save(_aisle(created, is_active=False, code="ZONE-9"))
    aisle_repo.save_calls = 0
    uc = ActivateAisleUseCase(aisle_repo=aisle_repo, clock=FixedClock(now))

    result = uc.execute(ActivateAisleCommand(inventory_id="inv-1", aisle_id="a1"))

    assert result.is_active is True
    assert result.code == "ZONE-9"
    assert result.updated_at == now
    assert aisle_repo.save_calls == 1


def test_inactive_aisle_still_has_code() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    aisle_repo = StubAisleRepo()
    aisle_repo.save(_aisle(now, code="HIST-CODE"))
    aisle_repo.save_calls = 0
    uc = _deactivate_uc(aisle_repo, StubJobRepo(), FixedClock(now))

    result = uc.execute(DeactivateAisleCommand(inventory_id="inv-1", aisle_id="a1"))

    assert result.is_active is False
    assert result.code == "HIST-CODE"
    found = aisle_repo.get_by_inventory_and_code("inv-1", "HIST-CODE")
    assert found is not None
    assert found.id == "a1"
