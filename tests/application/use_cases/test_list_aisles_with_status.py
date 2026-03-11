"""Tests for ListAislesWithStatusUseCase (batch job loading, no N+1)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Optional, Sequence

import pytest

from src.application.use_cases.list_aisles_with_status import AisleWithLatestJob, ListAislesWithStatusUseCase
from src.application.use_cases.create_aisle import InventoryNotFoundError
from src.application.ports.repositories import AisleRepository, InventoryRepository, JobRepository
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.domain.jobs.entities import Job, JobStatus


class StubInventoryRepo(InventoryRepository):
    def __init__(self, inventory_ids: set[str] | None = None) -> None:
        self._ids = inventory_ids or set()

    def save(self, inventory: Inventory) -> None:
        self._ids.add(inventory.id)

    def get_by_id(self, inventory_id: str) -> Optional[Inventory]:
        if inventory_id in self._ids:
            now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
            return Inventory(inventory_id, "Stub", InventoryStatus.DRAFT, now, now)
        return None

    def list_all(self) -> Sequence[Inventory]:
        return []


class StubAisleRepo(AisleRepository):
    def __init__(self, aisles: list[Aisle] | None = None) -> None:
        self._store = {a.id: a for a in (aisles or [])}

    def save(self, aisle: Aisle) -> None:
        self._store[aisle.id] = aisle

    def get_by_id(self, aisle_id: str) -> Optional[Aisle]:
        return self._store.get(aisle_id)

    def list_by_inventory(self, inventory_id: str) -> Sequence[Aisle]:
        return [a for a in self._store.values() if a.inventory_id == inventory_id]

    def get_by_inventory_and_code(self, inventory_id: str, code: str) -> Optional[Aisle]:
        for a in self._store.values():
            if a.inventory_id == inventory_id and a.code == code:
                return a
        return None


class StubJobRepo(JobRepository):
    def __init__(self, latest_by_aisle: Dict[str, Job] | None = None) -> None:
        self._latest = latest_by_aisle or {}

    def save(self, job: Job) -> None:
        pass

    def get_by_id(self, job_id: str) -> Optional[Job]:
        return None

    def get_latest_by_target(self, target_type: str, target_id: str) -> Optional[Job]:
        if target_type != "aisle":
            return None
        return self._latest.get(target_id)

    def get_latest_by_targets(
        self, target_type: str, target_ids: Sequence[str]
    ) -> Dict[str, Job]:
        if target_type != "aisle":
            return {}
        return {tid: self._latest[tid] for tid in target_ids if tid in self._latest}


def test_list_aisles_with_status_returns_aisles_and_latest_jobs() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    a1 = Aisle("a1", "inv-1", "A-01", AisleStatus.CREATED, now, now)
    a2 = Aisle("a2", "inv-1", "A-02", AisleStatus.CREATED, now, now)
    j1 = Job(
        "j1",
        "aisle",
        "a1",
        "process_aisle",
        JobStatus.RUNNING,
        {},
        now,
        now,
    )
    inv_repo = StubInventoryRepo({"inv-1"})
    aisle_repo = StubAisleRepo([a1, a2])
    job_repo = StubJobRepo({"a1": j1})

    use_case = ListAislesWithStatusUseCase(
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        job_repo=job_repo,
    )
    result = use_case.execute("inv-1")

    assert len(result) == 2
    by_id = {r.aisle.id: r for r in result}
    assert by_id["a1"].latest_job is not None
    assert by_id["a1"].latest_job.id == "j1"
    assert by_id["a2"].latest_job is None


def test_list_aisles_with_status_raises_when_inventory_not_found() -> None:
    inv_repo = StubInventoryRepo(set())
    aisle_repo = StubAisleRepo([])
    job_repo = StubJobRepo()
    use_case = ListAislesWithStatusUseCase(
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        job_repo=job_repo,
    )

    with pytest.raises(InventoryNotFoundError):
        use_case.execute("nonexistent")
