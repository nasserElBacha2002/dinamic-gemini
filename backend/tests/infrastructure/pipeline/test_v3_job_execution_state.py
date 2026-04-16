"""Focused tests for :class:`V3JobExecutionStateService` (Phase 2 job lifecycle split)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, Sequence
from unittest.mock import MagicMock

import pytest

from src.application.ports.clock import Clock
from src.application.ports.repositories import AisleRepository, InventoryRepository, JobRepository
from src.application.services.inventory_status_reconciler import InventoryStatusReconciler
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.inventory.entities import Inventory, InventoryProcessingMode, InventoryStatus
from src.domain.jobs.entities import Job, JobStatus
from src.infrastructure.pipeline.v3_job_execution_state import V3JobExecutionStateService
from src.pipeline.errors import PipelineCancellationRequestedError
from src.pipeline.execution_log import ExecutionLogWriter


class _FixedClock(Clock):
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


class _MemJobRepo(JobRepository):
    def __init__(self) -> None:
        self._store: Dict[str, Job] = {}

    def save(self, job: Job) -> None:
        self._store[job.id] = job

    def get_by_id(self, job_id: str) -> Optional[Job]:
        return self._store.get(job_id)

    def get_latest_by_target(self, target_type: str, target_id: str) -> Optional[Job]:
        return None

    def get_latest_by_targets(self, target_type: str, target_ids: Sequence[str]) -> Dict[str, Job]:
        return {}

    def list_jobs_for_target(self, target_type: str, target_id: str, *, limit: int = 50) -> Sequence[Job]:
        return []


class _MemAisleRepo(AisleRepository):
    def __init__(self) -> None:
        self._store: Dict[str, Aisle] = {}

    def save(self, aisle: Aisle) -> None:
        self._store[aisle.id] = aisle

    def get_by_id(self, aisle_id: str) -> Optional[Aisle]:
        return self._store.get(aisle_id)

    def list_by_inventory(self, inventory_id: str) -> Sequence[Aisle]:
        return [a for a in self._store.values() if a.inventory_id == inventory_id]

    def get_by_inventory_and_code(self, inventory_id: str, code: str) -> Optional[Aisle]:
        return None


class _MemInventoryRepo(InventoryRepository):
    def __init__(self, inventory: Inventory) -> None:
        self._inventory = inventory

    def save(self, inventory: Inventory) -> None:
        self._inventory = inventory

    def get_by_id(self, inventory_id: str) -> Optional[Inventory]:
        if self._inventory.id == inventory_id:
            return self._inventory
        return None

    def list_all(self) -> Sequence[Inventory]:
        return [self._inventory]


def _make_svc(
    *,
    inventory_mode: InventoryProcessingMode = InventoryProcessingMode.TEST,
) -> tuple[V3JobExecutionStateService, _MemJobRepo, _MemAisleRepo, datetime, MagicMock]:
    now = datetime(2026, 1, 10, 12, 0, 0, tzinfo=timezone.utc)
    clock = _FixedClock(now)
    job_repo = _MemJobRepo()
    aisle_repo = _MemAisleRepo()
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    inv = Inventory(
        id="inv-1",
        name="Inv",
        status=InventoryStatus.PROCESSING,
        created_at=t0,
        updated_at=t0,
        processing_mode=inventory_mode,
    )
    inventory_repo = _MemInventoryRepo(inv)
    reconciler = MagicMock(spec=InventoryStatusReconciler)
    svc = V3JobExecutionStateService(
        job_repo=job_repo,
        aisle_repo=aisle_repo,
        inventory_repo=inventory_repo,
        clock=clock,
        inventory_status_reconciler=reconciler,
    )
    return svc, job_repo, aisle_repo, now, reconciler


def test_mark_running_sets_job_running_and_reconciles_inventory() -> None:
    svc, job_repo, aisle_repo, now, reconciler = _make_svc()
    job = Job(
        id="job-1",
        job_type="process_aisle",
        target_type="aisle",
        target_id="aisle-1",
        status=JobStatus.STARTING,
        payload_json={"aisle_id": "aisle-1"},
        created_at=now,
        updated_at=now,
        attempt_count=1,
        execution_id="ex-1",
    )
    job_repo.save(job)
    aisle = Aisle(
        id="aisle-1",
        inventory_id="inv-1",
        code="A1",
        status=AisleStatus.QUEUED,
        created_at=now,
        updated_at=now,
    )
    aisle_repo.save(aisle)

    svc.mark_running("job-1", aisle, now)

    saved_job = job_repo.get_by_id("job-1")
    assert saved_job is not None
    assert saved_job.status == JobStatus.RUNNING
    assert saved_job.current_stage == "Pipeline"
    assert saved_job.current_substep == "startup_confirmed"
    saved_aisle = aisle_repo.get_by_id("aisle-1")
    assert saved_aisle is not None
    assert saved_aisle.status == AisleStatus.PROCESSING
    reconciler.reconcile.assert_called_once_with("inv-1")


def test_fail_job_and_aisle_marks_failed_and_reconciles() -> None:
    svc, job_repo, aisle_repo, _, _ = _make_svc()
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    job = Job(
        id="job-1",
        job_type="process_aisle",
        target_type="aisle",
        target_id="aisle-1",
        status=JobStatus.RUNNING,
        payload_json={},
        created_at=t0,
        updated_at=t0,
        attempt_count=1,
        execution_id="ex-1",
    )
    job_repo.save(job)
    aisle = Aisle(
        id="aisle-1",
        inventory_id="inv-1",
        code="A1",
        status=AisleStatus.PROCESSING,
        created_at=t0,
        updated_at=t0,
    )
    aisle_repo.save(aisle)

    svc.fail_job_and_aisle("job-1", aisle, "boom")

    saved_job = job_repo.get_by_id("job-1")
    assert saved_job is not None
    assert saved_job.status == JobStatus.FAILED
    assert saved_job.failure_code == "PROCESSING_FAILED"
    saved_aisle = aisle_repo.get_by_id("aisle-1")
    assert saved_aisle is not None
    assert saved_aisle.status == AisleStatus.FAILED
    assert saved_aisle.error_code == "PROCESSING_FAILED"


def test_raise_if_cancellation_requested_emits_and_raises(tmp_path: Path) -> None:
    svc, job_repo, _, _, _ = _make_svc()
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    job = Job(
        id="job-1",
        job_type="process_aisle",
        target_type="aisle",
        target_id="aisle-1",
        status=JobStatus.CANCEL_REQUESTED,
        payload_json={},
        created_at=t0,
        updated_at=t0,
        attempt_count=2,
        execution_id="ex-1",
        cancel_requested_at=datetime(2026, 1, 9, tzinfo=timezone.utc),
    )
    job_repo.save(job)
    exec_log = ExecutionLogWriter(tmp_path)
    emitted: Dict[str, bool] = {"requested": False, "detected": False, "cancelled": False}

    with pytest.raises(PipelineCancellationRequestedError):
        svc.raise_if_cancellation_requested(
            "job-1",
            exec_log=exec_log,
            inventory_id="inv-1",
            aisle_id="aisle-1",
            stage="Pipeline",
            substep="pre_pipeline",
            reason="Job canceled before pipeline execution",
            cancel_event_emitted=emitted,
        )

    assert emitted["requested"] is True
    assert emitted["detected"] is True


def test_mark_success_sets_operational_job_id_in_production(tmp_path: Path) -> None:
    svc, job_repo, aisle_repo, _, _ = _make_svc(inventory_mode=InventoryProcessingMode.PRODUCTION)
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    job = Job(
        id="job-1",
        job_type="process_aisle",
        target_type="aisle",
        target_id="aisle-1",
        status=JobStatus.RUNNING,
        payload_json={},
        created_at=t0,
        updated_at=t0,
        attempt_count=1,
        execution_id="ex-1",
    )
    job_repo.save(job)
    aisle = Aisle(
        id="aisle-1",
        inventory_id="inv-1",
        code="A1",
        status=AisleStatus.PROCESSING,
        created_at=t0,
        updated_at=t0,
    )
    aisle_repo.save(aisle)

    svc.mark_success(
        "job-1",
        aisle,
        report_path=tmp_path / "hybrid_report.json",
        run_metadata={"provider": "x", "prompt_key": "pk"},
        durable_artifacts=None,
    )

    saved_aisle = aisle_repo.get_by_id("aisle-1")
    assert saved_aisle is not None
    assert saved_aisle.operational_job_id == "job-1"
    assert saved_aisle.status == AisleStatus.PROCESSED
    saved_job = job_repo.get_by_id("job-1")
    assert saved_job is not None
    assert saved_job.status == JobStatus.SUCCEEDED
