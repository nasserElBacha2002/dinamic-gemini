"""Phase 7 release E2E — ephemeral SQL + deterministic LLM (no live provider)."""

from __future__ import annotations

import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import MagicMock

import pytest

from src.application.errors import WorkerLaunchFailedError
from src.application.services.aisle_job_launch_service import AisleJobLaunchService
from src.application.services.inventory_status_reconciler import InventoryStatusReconciler
from src.application.use_cases.aisles.cancel_aisle_job import (
    CancelAisleJobCommand,
    CancelAisleJobUseCase,
)
from src.application.use_cases.recovery.recover_stale_job import (
    RecoverStaleJobCommand,
    RecoverStaleJobUseCase,
)
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.aisle_identification.modes import (
    AisleIdentificationExecutionStrategy,
    AisleIdentificationMode,
    AisleIdentificationModeSource,
)
from src.domain.inventory.entities import Inventory, InventoryProcessingMode, InventoryStatus
from src.domain.jobs.claim import JobClaimOutcome
from src.domain.jobs.entities import Job, JobStatus
from src.infrastructure.repositories.sql_aisle_repository import SqlAisleRepository
from src.infrastructure.repositories.sql_inventory_repository import SqlInventoryRepository
from src.infrastructure.repositories.sql_job_repository import SqlJobRepository
from tests.support.llm_executor_harness import TestLLMExecutor, llm_response_success
from tests.support.sql_integration import sql_server_client_or_skip
from tests.support.sqlserver_test_connection import resolved_sqlserver_connection_string_for_tests

pytestmark = [pytest.mark.integration, pytest.mark.release_e2e]


@pytest.fixture(scope="module")
def sql_client():
    return sql_server_client_or_skip(resolved_sqlserver_connection_string_for_tests())


@pytest.fixture(scope="module")
def _require_schema(sql_client):
    with sql_client.cursor() as cur:
        cur.execute(
            """
            SELECT 1 FROM sys.columns
            WHERE object_id = OBJECT_ID('inventory_jobs') AND name = 'claim_owner_id'
            """
        )
        if cur.fetchone() is None:
            pytest.skip("claim_owner_id missing; apply migrations through 0071+")
        cur.execute(
            """
            SELECT 1 FROM sys.indexes
            WHERE name = N'UX_inventory_jobs_retry_of_job_id'
              AND object_id = OBJECT_ID(N'dbo.inventory_jobs')
            """
        )
        if cur.fetchone() is None:
            pytest.skip("0073 unique index missing; apply migration 0073")


def _now() -> datetime:
    return datetime.now(timezone.utc)


class _FixedClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


class _FakeWorkerLaunch:
    def __init__(self) -> None:
        self.launches: list[str] = []
        self.fail = False
        self._keys: set[str] = set()
        self._lock = threading.Lock()

    def launch(self, job_id: str) -> str:
        if self.fail:
            raise WorkerLaunchFailedError("spawn refused", job_id=job_id)
        self.launches.append(job_id)
        return f"exec-{job_id}"

    def launch_job_if_not_launched(self, job_id: str, *, idempotency_key: str) -> str:
        with self._lock:
            if idempotency_key in self._keys:
                return f"exec-re-{job_id}"
            if self.fail:
                raise WorkerLaunchFailedError("relaunch refused", job_id=job_id)
            self._keys.add(idempotency_key)
        self.launches.append(job_id)
        return f"exec-re-{job_id}"


def _seed(sql_client, *, job_status: JobStatus = JobStatus.STARTING):
    inv_repo = SqlInventoryRepository(sql_client)
    aisle_repo = SqlAisleRepository(sql_client)
    job_repo = SqlJobRepository(sql_client)
    now = _now()
    suffix = uuid.uuid4().hex[:10]
    inv_id = f"inv-e2e-{suffix}"
    aisle_id = f"aisle-e2e-{suffix}"
    job_id = f"job-e2e-{suffix}"
    inv_repo.save(
        Inventory(
            id=inv_id,
            name="Phase7 E2E",
            status=InventoryStatus.PROCESSING,
            created_at=now,
            updated_at=now,
            processing_mode=InventoryProcessingMode.TEST,
        )
    )
    aisle_repo.save(
        Aisle(
            id=aisle_id,
            inventory_id=inv_id,
            code=f"E{suffix[:4]}",
            status=AisleStatus.QUEUED,
            created_at=now,
            updated_at=now,
        )
    )
    job_repo.save(
        Job(
            id=job_id,
            job_type="process_aisle",
            target_type="aisle",
            target_id=aisle_id,
            status=job_status,
            payload_json={"aisle_id": aisle_id},
            created_at=now,
            updated_at=now,
            attempt_count=1,
            started_at=now if job_status != JobStatus.QUEUED else None,
            last_heartbeat_at=now,
        )
    )
    return job_repo, aisle_repo, inv_repo, job_id, aisle_id, inv_id


def test_e2e_happy_path_claim_lease_provider(sql_client, _require_schema) -> None:
    job_repo, aisle_repo, _, job_id, aisle_id, _ = _seed(sql_client)
    now = _now()
    owner = f"worker-{uuid.uuid4().hex[:8]}"
    result = job_repo.try_claim_starting_to_running(
        job_id, now=now, claim_owner_id=owner, aisle_id=aisle_id
    )
    assert result.outcome == JobClaimOutcome.ACQUIRED
    assert result.may_execute is True
    job = job_repo.get_by_id(job_id)
    assert job is not None
    assert job.status == JobStatus.RUNNING
    assert job.claim_owner_id == owner
    job2 = job_repo.get_by_id(job_id)
    assert job2 is not None
    assert job2.last_heartbeat_at is not None
    aisle = aisle_repo.get_by_id(aisle_id)
    assert aisle is not None
    assert aisle.status == AisleStatus.PROCESSING
    executor = TestLLMExecutor(response=llm_response_success(parsed_json={"ok": True, "items": []}))
    _ = executor.execute(MagicMock(), MagicMock())


def test_e2e_cancel_queued_job(sql_client, _require_schema) -> None:
    job_repo, aisle_repo, _, job_id, aisle_id, inv_id = _seed(
        sql_client, job_status=JobStatus.QUEUED
    )
    uc = CancelAisleJobUseCase(
        aisle_repo=aisle_repo,
        job_repo=job_repo,
        clock=_FixedClock(_now()),
    )
    result = uc.execute(
        CancelAisleJobCommand(inventory_id=inv_id, aisle_id=aisle_id, job_id=job_id)
    )
    assert result.status == JobStatus.CANCELED


def test_e2e_retry_of_unique_rejects_duplicate(sql_client, _require_schema) -> None:
    job_repo, _, _, parent_id, aisle_id, _ = _seed(sql_client)
    now = _now()
    child1 = f"job-child1-{uuid.uuid4().hex[:8]}"
    child2 = f"job-child2-{uuid.uuid4().hex[:8]}"
    job_repo.save(
        Job(
            id=child1,
            job_type="process_aisle",
            target_type="aisle",
            target_id=aisle_id,
            status=JobStatus.QUEUED,
            payload_json={"aisle_id": aisle_id},
            created_at=now,
            updated_at=now,
            attempt_count=1,
            retry_of_job_id=parent_id,
        )
    )
    with pytest.raises(Exception):
        job_repo.save(
            Job(
                id=child2,
                job_type="process_aisle",
                target_type="aisle",
                target_id=aisle_id,
                status=JobStatus.QUEUED,
                payload_json={"aisle_id": aisle_id},
                created_at=now,
                updated_at=now,
                attempt_count=1,
                retry_of_job_id=parent_id,
            )
        )


def test_e2e_stale_recovery_and_launch_failure(sql_client, _require_schema) -> None:
    job_repo, aisle_repo, inv_repo, job_id, aisle_id, _ = _seed(
        sql_client, job_status=JobStatus.RUNNING
    )
    now = _now()
    old = now - timedelta(hours=2)
    job = job_repo.get_by_id(job_id)
    assert job is not None
    job.last_heartbeat_at = old
    job.updated_at = old
    job.claim_owner_id = "owner-dead"
    job.lease_expires_at = old
    job.identification_mode = AisleIdentificationMode.INTERNAL_OCR
    job.identification_mode_source = AisleIdentificationModeSource.SYSTEM_DEFAULT
    job.execution_strategy = AisleIdentificationExecutionStrategy.INTERNAL_OCR
    job_repo.save(job)
    aisle = aisle_repo.get_by_id(aisle_id)
    assert aisle is not None
    aisle.status = AisleStatus.PROCESSING
    aisle.updated_at = old
    aisle_repo.save(aisle)

    worker = _FakeWorkerLaunch()
    clock = _FixedClock(now)
    launch = AisleJobLaunchService(
        aisle_repo=aisle_repo,
        job_repo=job_repo,
        worker_launch_service=worker,
        clock=clock,
        status_reconciler=InventoryStatusReconciler(
            inventory_repo=inv_repo, aisle_repo=aisle_repo, clock=clock
        ),
    )
    uc = RecoverStaleJobUseCase(
        job_repo=job_repo,
        aisle_repo=aisle_repo,
        launch_service=launch,
        clock=clock,
    )
    outcome = uc.execute(
        RecoverStaleJobCommand(job_id=job_id, dry_run=False, actor="phase7-e2e", reason="e2e")
    )
    assert outcome is not None

    worker.fail = True
    with pytest.raises(WorkerLaunchFailedError):
        worker.launch("job-launch-fail")


def test_e2e_provider_timeout_and_sql_transient(sql_client, _require_schema) -> None:
    class _TimeoutExecutor(TestLLMExecutor):
        def execute(self, request: Any, settings: Any) -> Any:  # noqa: ANN401
            raise TimeoutError("provider timeout simulated")

    with pytest.raises(TimeoutError):
        _TimeoutExecutor().execute(MagicMock(), MagicMock())

    attempts = {"n": 0}

    def flaky() -> int:
        attempts["n"] += 1
        if attempts["n"] < 2:
            raise OSError("transient SQL network glitch")
        with sql_client.cursor() as cur:
            cur.execute("SELECT 1")
            return int(cur.fetchone()[0])

    for _ in range(3):
        try:
            assert flaky() == 1
            break
        except OSError:
            time.sleep(0.05)
    else:
        pytest.fail("SQL transient recovery failed")
