"""SQL integration: RecoverStaleJobUseCase idempotency (real SQL Server)."""

from __future__ import annotations

import threading
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from src.application.services.aisle_job_launch_service import AisleJobLaunchService
from src.application.services.inventory_status_reconciler import InventoryStatusReconciler
from src.application.use_cases.recovery.recover_stale_job import (
    RecoverStaleJobCommand,
    RecoverStaleJobOutcome,
    RecoverStaleJobUseCase,
)
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.aisle_identification.modes import (
    AisleIdentificationExecutionStrategy,
    AisleIdentificationMode,
    AisleIdentificationModeSource,
)
from src.domain.inventory.entities import Inventory, InventoryProcessingMode, InventoryStatus
from src.domain.jobs.entities import Job, JobStatus
from src.infrastructure.repositories.sql_aisle_repository import SqlAisleRepository
from src.infrastructure.repositories.sql_inventory_repository import SqlInventoryRepository
from src.infrastructure.repositories.sql_job_repository import SqlJobRepository
from tests.support.sql_integration import sql_server_client_or_skip
from tests.support.sqlserver_test_connection import resolved_sqlserver_connection_string_for_tests

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def sql_client():
    return sql_server_client_or_skip(resolved_sqlserver_connection_string_for_tests())


@pytest.fixture(scope="module")
def _require_retry_of(sql_client):
    with sql_client.cursor() as cur:
        cur.execute(
            """
            SELECT 1 FROM sys.columns
            WHERE object_id = OBJECT_ID('inventory_jobs') AND name = 'retry_of_job_id'
            """
        )
        if cur.fetchone() is None:
            pytest.skip("retry_of_job_id missing; apply migrations")
        # Ensure Phase 5 unique index exists (idempotent).
        cur.execute(
            """
            IF NOT EXISTS (
                SELECT 1 FROM sys.indexes
                WHERE name = N'UX_inventory_jobs_retry_of_job_id'
                  AND object_id = OBJECT_ID(N'dbo.inventory_jobs')
            )
            BEGIN
                CREATE UNIQUE NONCLUSTERED INDEX UX_inventory_jobs_retry_of_job_id
                    ON dbo.inventory_jobs(retry_of_job_id)
                    WHERE retry_of_job_id IS NOT NULL;
            END
            """
        )


class _FixedClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


class _FakeWorkerLaunch:
    def __init__(self) -> None:
        self.launches: list[str] = []
        self.idempotent_launches: list[tuple[str, str]] = []
        self._idempotency_keys: set[str] = set()

    def launch(self, job_id: str) -> str:
        self.launches.append(job_id)
        return f"exec-{job_id}"

    def launch_job_if_not_launched(self, job_id: str, *, idempotency_key: str) -> str:
        if idempotency_key in self._idempotency_keys:
            return f"exec-relaunch-{job_id}"
        self._idempotency_keys.add(idempotency_key)
        self.idempotent_launches.append((job_id, idempotency_key))
        return f"exec-relaunch-{job_id}"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def test_sql_two_recoverers_one_retry_one_worker(sql_client, _require_retry_of) -> None:
    now = _now()
    clock = _FixedClock(now)
    inv_repo = SqlInventoryRepository(sql_client)
    aisle_repo = SqlAisleRepository(sql_client)
    job_repo = SqlJobRepository(sql_client)
    worker = _FakeWorkerLaunch()
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

    suffix = uuid.uuid4().hex[:10]
    inv_id = f"inv-rec-{suffix}"
    aisle_id = f"aisle-rec-{suffix}"
    job_id = f"job-rec-{suffix}"
    old = now - timedelta(hours=3)
    inv_repo.save(
        Inventory(
            id=inv_id,
            name="Recovery IT",
            status=InventoryStatus.PROCESSING,
            created_at=old,
            updated_at=old,
            processing_mode=InventoryProcessingMode.TEST,
        )
    )
    aisle_repo.save(
        Aisle(
            id=aisle_id,
            inventory_id=inv_id,
            code=f"R{suffix[:4]}",
            status=AisleStatus.PROCESSING,
            created_at=old,
            updated_at=old,
        )
    )
    job_repo.save(
        Job(
            id=job_id,
            target_type="aisle",
            target_id=aisle_id,
            job_type="process_aisle",
            status=JobStatus.RUNNING,
            payload_json={"aisle_id": aisle_id, "correlation_id": f"corr-{suffix}"},
            created_at=old,
            updated_at=old,
            started_at=old,
            last_heartbeat_at=old,
            attempt_count=1,
            claim_owner_id="owner-dead",
            lease_expires_at=old,
            provider_name="gemini",
            identification_mode=AisleIdentificationMode.INTERNAL_OCR,
            identification_mode_source=AisleIdentificationModeSource.SYSTEM_DEFAULT,
            execution_strategy=AisleIdentificationExecutionStrategy.INTERNAL_OCR,
        )
    )

    barrier = threading.Barrier(2)
    outcomes: list[RecoverStaleJobOutcome] = []
    lock = threading.Lock()

    def run() -> None:
        barrier.wait()
        try:
            result = uc.execute(
                RecoverStaleJobCommand(
                    job_id=job_id,
                    actor="sql-test",
                    reason="stale",
                    dry_run=False,
                    stale_after_seconds=60,
                    max_attempts=5,
                )
            )
            with lock:
                outcomes.append(result.outcome)
        except Exception:
            with lock:
                outcomes.append(RecoverStaleJobOutcome.LOST_CAS)

    threads = [threading.Thread(target=run) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Deadlock victims count as LOST_CAS; still exactly one successful recovery child.
    assert outcomes.count(RecoverStaleJobOutcome.RECOVERED) == 1
    assert (
        outcomes.count(RecoverStaleJobOutcome.ALREADY_RECOVERED)
        + outcomes.count(RecoverStaleJobOutcome.LOST_CAS)
        == 1
    )
    children = list(job_repo.list_jobs_by_retry_of(job_id))
    assert len(children) == 1
    assert children[0].payload_json.get("correlation_id") == f"corr-{suffix}"
    assert len(worker.launches) == 1
    parent = job_repo.get_by_id(job_id)
    assert parent is not None
    assert parent.status == JobStatus.FAILED


class _FailThenOkWorkerLaunch:
    def __init__(self) -> None:
        self.launches: list[str] = []
        self.idempotent_launches: list[tuple[str, str]] = []
        self._fail_first = True
        self._idempotency_keys: set[str] = set()

    def launch(self, job_id: str) -> str:
        if self._fail_first:
            from src.application.errors import WorkerLaunchFailedError

            raise WorkerLaunchFailedError("spawn refused", job_id=job_id)
        self.launches.append(job_id)
        return f"exec-{job_id}"

    def launch_job_if_not_launched(self, job_id: str, *, idempotency_key: str) -> str:
        if idempotency_key in self._idempotency_keys:
            return f"exec-relaunch-{job_id}"
        self._idempotency_keys.add(idempotency_key)
        self.idempotent_launches.append((job_id, idempotency_key))
        return f"exec-relaunch-{job_id}"


def test_sql_launch_failure_then_relaunch(sql_client, _require_retry_of) -> None:
    now = _now()
    clock = _FixedClock(now)
    inv_repo = SqlInventoryRepository(sql_client)
    aisle_repo = SqlAisleRepository(sql_client)
    job_repo = SqlJobRepository(sql_client)
    worker = _FailThenOkWorkerLaunch()
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

    suffix = uuid.uuid4().hex[:10]
    inv_id = f"inv-rel-{suffix}"
    aisle_id = f"aisle-rel-{suffix}"
    job_id = f"job-rel-{suffix}"
    old = now - timedelta(hours=3)
    inv_repo.save(
        Inventory(
            id=inv_id,
            name="Relaunch IT",
            status=InventoryStatus.PROCESSING,
            created_at=old,
            updated_at=old,
            processing_mode=InventoryProcessingMode.TEST,
        )
    )
    aisle_repo.save(
        Aisle(
            id=aisle_id,
            inventory_id=inv_id,
            code=f"R{suffix[:4]}",
            status=AisleStatus.PROCESSING,
            created_at=old,
            updated_at=old,
        )
    )
    job_repo.save(
        Job(
            id=job_id,
            target_type="aisle",
            target_id=aisle_id,
            job_type="process_aisle",
            status=JobStatus.RUNNING,
            payload_json={"aisle_id": aisle_id, "correlation_id": f"corr-{suffix}"},
            created_at=old,
            updated_at=old,
            started_at=old,
            last_heartbeat_at=old,
            attempt_count=1,
            claim_owner_id="owner-dead",
            lease_expires_at=old,
            provider_name="gemini",
            identification_mode=AisleIdentificationMode.INTERNAL_OCR,
            identification_mode_source=AisleIdentificationModeSource.SYSTEM_DEFAULT,
            execution_strategy=AisleIdentificationExecutionStrategy.INTERNAL_OCR,
        )
    )

    first = uc.execute(
        RecoverStaleJobCommand(
            job_id=job_id,
            actor="sql-test",
            reason="stale",
            dry_run=False,
            stale_after_seconds=60,
            max_attempts=5,
        )
    )
    assert first.outcome == RecoverStaleJobOutcome.WORKER_LAUNCH_FAILED
    child = list(job_repo.list_jobs_by_retry_of(job_id))[0]
    assert child.failure_code == "WORKER_LAUNCH_FAILED"

    worker._fail_first = False
    second = uc.execute(
        RecoverStaleJobCommand(
            job_id=job_id,
            actor="sql-test",
            reason="stale",
            dry_run=False,
            stale_after_seconds=60,
            max_attempts=5,
        )
    )
    assert second.outcome == RecoverStaleJobOutcome.RELAUNCHED
    assert second.new_job_id == child.id
    assert len(worker.idempotent_launches) == 1
