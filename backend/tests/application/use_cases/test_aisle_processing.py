"""Tests for StartAisleProcessingUseCase and GetAisleProcessingStatusUseCase."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Optional, Sequence

import pytest

from src.application.ports.repositories import AisleRepository, InventoryRepository, JobRepository
from src.application.services.aisle_job_launch_service import AisleJobLaunchService
from src.application.services.inventory_status_reconciler import InventoryStatusReconciler
from src.application.services.job_stale_reconciler import (
    JobStaleReconciler,
    STALE_FAILURE_CODE,
    STALE_FAILURE_MESSAGE,
)
from src.application.ports.services import WorkerLaunchService
from src.application.errors import ActiveJobExistsError, AisleNotFoundError, InventoryNotFoundError
from src.application.use_cases.get_aisle_processing_status import GetAisleProcessingStatusUseCase
from src.application.use_cases.start_aisle_processing import (
    StartAisleProcessingCommand,
    StartAisleProcessingUseCase,
)
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.domain.jobs.entities import Job, JobStatus
from tests.support.processing_test_constants import STUB_PRIMARY_MODEL, STUB_PRIMARY_PROVIDER


class FixedClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


class StubInventoryRepo(InventoryRepository):
    def __init__(self, inventories: list[Inventory] | None = None) -> None:
        self._store = {i.id: i for i in (inventories or [])}

    def save(self, inventory: Inventory) -> None:
        self._store[inventory.id] = inventory

    def get_by_id(self, inventory_id: str) -> Optional[Inventory]:
        return self._store.get(inventory_id)

    def list_all(self) -> Sequence[Inventory]:
        return list(self._store.values())


class StubAisleRepo(AisleRepository):
    def __init__(self) -> None:
        self._store: Dict[str, Aisle] = {}

    def save(self, aisle: Aisle) -> None:
        self._store[aisle.id] = aisle

    def get_by_id(self, aisle_id: str) -> Optional[Aisle]:
        return self._store.get(aisle_id)

    def list_by_inventory(self, inventory_id: str) -> Sequence[Aisle]:
        return [a for a in self._store.values() if a.inventory_id == inventory_id]

    def get_by_inventory_and_code(self, inventory_id: str, code: str) -> Optional[Aisle]:
        for a in self._store.values():
            if a.inventory_id == inventory_id and a.code == code.strip():
                return a
        return None


class StubJobRepo(JobRepository):
    def __init__(self) -> None:
        self._store: Dict[str, Job] = {}

    def save(self, job: Job) -> None:
        self._store[job.id] = job

    def get_by_id(self, job_id: str) -> Optional[Job]:
        return self._store.get(job_id)

    def get_latest_by_target(self, target_type: str, target_id: str) -> Optional[Job]:
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
    ) -> Dict[str, Job]:
        out: Dict[str, Job] = {}
        for tid in target_ids:
            latest = self.get_latest_by_target(target_type, tid)
            if latest is not None:
                out[tid] = latest
        return out

    def list_jobs_for_target(
        self, target_type: str, target_id: str, *, limit: int = 50
    ) -> Sequence[Job]:
        candidates = [
            j
            for j in self._store.values()
            if j.target_type == target_type and j.target_id == target_id
        ]
        candidates.sort(key=lambda j: (j.updated_at, j.created_at), reverse=True)
        n = max(1, int(limit))
        return candidates[:n]


class StubWorkerLaunchService(WorkerLaunchService):
    def __init__(self) -> None:
        self.launched: list[str] = []

    def launch(self, job_id: str) -> str:
        self.launched.append(job_id)
        return f"exec-{job_id}"


def make_stale_reconciler(job_repo: JobRepository, clock: FixedClock, stale_after_seconds: int = 900) -> JobStaleReconciler:
    return JobStaleReconciler(
        job_repo=job_repo,
        clock=clock,
        stale_after_seconds=stale_after_seconds,
    )


def make_launch_service(
    *,
    aisle_repo: AisleRepository,
    job_repo: JobRepository,
    worker_launch_service: WorkerLaunchService,
    clock: FixedClock,
    reconciler: InventoryStatusReconciler,
) -> AisleJobLaunchService:
    return AisleJobLaunchService(
        aisle_repo=aisle_repo,
        job_repo=job_repo,
        worker_launch_service=worker_launch_service,
        clock=clock,
        status_reconciler=reconciler,
    )


def test_start_aisle_processing_creates_job_and_marks_aisle_queued() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    inv_repo = StubInventoryRepo([Inventory("inv1", "W", InventoryStatus.DRAFT, now, now)])
    aisle = Aisle("a1", "inv1", "A01", AisleStatus.CREATED, now, now)
    aisle_repo = StubAisleRepo()
    aisle_repo.save(aisle)
    job_repo = StubJobRepo()
    queue = StubWorkerLaunchService()
    clock = FixedClock(now)
    reconciler = InventoryStatusReconciler(inv_repo, aisle_repo, clock)

    use_case = StartAisleProcessingUseCase(
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        job_repo=job_repo,
        launch_service=make_launch_service(
            aisle_repo=aisle_repo,
            job_repo=job_repo,
            worker_launch_service=queue,
            clock=clock,
            reconciler=reconciler,
        ),
        stale_reconciler=make_stale_reconciler(job_repo, clock),
    )
    job_id = use_case.execute(StartAisleProcessingCommand(inventory_id="inv1", aisle_id="a1"))
    assert queue.launched == [job_id]
    saved_job = job_repo.get_by_id(job_id)
    assert saved_job is not None
    assert saved_job.provider_name == "gemini"
    assert saved_job.prompt_key == "global_v21"
    assert saved_job.target_type == "aisle"
    assert saved_job.target_id == "a1"
    assert saved_job.job_type == "process_aisle"
    assert saved_job.status == JobStatus.STARTING
    assert saved_job.payload_json == {"aisle_id": "a1"}
    assert saved_job.execution_id == f"exec-{job_id}"
    assert saved_job.current_substep == "spawn_succeeded"

    updated_aisle = aisle_repo.get_by_id("a1")
    assert updated_aisle is not None
    assert updated_aisle.status == AisleStatus.QUEUED
    assert inv_repo.get_by_id("inv1") is not None
    assert inv_repo.get_by_id("inv1").status == InventoryStatus.PROCESSING


def test_start_aisle_processing_persists_explicit_provider_and_prompt() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    inv_repo = StubInventoryRepo([Inventory("inv1", "W", InventoryStatus.DRAFT, now, now)])
    aisle = Aisle("a1", "inv1", "A01", AisleStatus.CREATED, now, now)
    aisle_repo = StubAisleRepo()
    aisle_repo.save(aisle)
    job_repo = StubJobRepo()
    queue = StubWorkerLaunchService()
    clock = FixedClock(now)
    reconciler = InventoryStatusReconciler(inv_repo, aisle_repo, clock)
    use_case = StartAisleProcessingUseCase(
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        job_repo=job_repo,
        launch_service=make_launch_service(
            aisle_repo=aisle_repo,
            job_repo=job_repo,
            worker_launch_service=queue,
            clock=clock,
            reconciler=reconciler,
        ),
        stale_reconciler=make_stale_reconciler(job_repo, clock),
    )
    job_id = use_case.execute(
        StartAisleProcessingCommand(
            inventory_id="inv1",
            aisle_id="a1",
            pipeline_provider_key=STUB_PRIMARY_PROVIDER,
            model_name=STUB_PRIMARY_MODEL,
            prompt_key="global_v21",
        )
    )
    saved = job_repo.get_by_id(job_id)
    assert saved is not None
    assert saved.provider_name == STUB_PRIMARY_PROVIDER
    assert saved.model_name == STUB_PRIMARY_MODEL
    assert saved.prompt_key == "global_v21"


def test_start_aisle_processing_persists_job_before_enqueue() -> None:
    """Regression test for the v3 queue race condition.

    The worker dequeues job ids from an in-memory queue. To avoid dequeuing a job
    before persistence, the use case must persist the job/aisle first, then enqueue.
    """
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    inv_repo = StubInventoryRepo([Inventory("inv1", "W", InventoryStatus.DRAFT, now, now)])
    aisle = Aisle("a1", "inv1", "A01", AisleStatus.CREATED, now, now)
    aisle_repo = StubAisleRepo()
    aisle_repo.save(aisle)
    job_repo = StubJobRepo()

    class AssertingLaunchService(WorkerLaunchService):
        def __init__(self) -> None:
            self.launched: list[str] = []

        def launch(self, job_id: str) -> str:
            assert job_repo.get_by_id(job_id) is not None
            self.launched.append(job_id)
            return f"exec-{job_id}"

    queue = AssertingLaunchService()
    clock = FixedClock(now)
    reconciler = InventoryStatusReconciler(inv_repo, aisle_repo, clock)
    use_case = StartAisleProcessingUseCase(
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        job_repo=job_repo,
        launch_service=make_launch_service(
            aisle_repo=aisle_repo,
            job_repo=job_repo,
            worker_launch_service=queue,
            clock=clock,
            reconciler=reconciler,
        ),
        stale_reconciler=make_stale_reconciler(job_repo, clock),
    )

    job_id = use_case.execute(StartAisleProcessingCommand(inventory_id="inv1", aisle_id="a1"))
    assert queue.launched == [job_id]


def test_start_aisle_processing_marks_failed_when_enqueue_fails() -> None:
    """If enqueue(job_id) fails, do not leave QUEUED job/aisle behind."""
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    inv_repo = StubInventoryRepo([Inventory("inv1", "W", InventoryStatus.DRAFT, now, now)])
    aisle = Aisle("a1", "inv1", "A01", AisleStatus.CREATED, now, now)
    aisle_repo = StubAisleRepo()
    aisle_repo.save(aisle)
    job_repo = StubJobRepo()

    class FailingQueue(WorkerLaunchService):
        def __init__(self) -> None:
            self.captured_job_id: str | None = None

        def launch(self, job_id: str) -> str:
            self.captured_job_id = job_id
            raise RuntimeError("in-memory queue failure")

    queue = FailingQueue()
    clock = FixedClock(now)
    reconciler = InventoryStatusReconciler(inv_repo, aisle_repo, clock)
    use_case = StartAisleProcessingUseCase(
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        job_repo=job_repo,
        launch_service=make_launch_service(
            aisle_repo=aisle_repo,
            job_repo=job_repo,
            worker_launch_service=queue,
            clock=clock,
            reconciler=reconciler,
        ),
        stale_reconciler=make_stale_reconciler(job_repo, clock),
    )

    with pytest.raises(RuntimeError):
        use_case.execute(StartAisleProcessingCommand(inventory_id="inv1", aisle_id="a1"))

    assert queue.captured_job_id is not None
    saved_job = job_repo.get_by_id(queue.captured_job_id)
    assert saved_job is not None
    assert saved_job.status == JobStatus.FAILED
    assert saved_job.error_message is not None
    assert "in-memory queue failure" in saved_job.error_message
    assert saved_job.failure_code == "WORKER_LAUNCH_FAILED"

    updated_aisle = aisle_repo.get_by_id("a1")
    assert updated_aisle is not None
    assert updated_aisle.status == AisleStatus.FAILED
    assert updated_aisle.error_message is not None
    assert "in-memory queue failure" in updated_aisle.error_message
    assert inv_repo.get_by_id("inv1") is not None
    assert inv_repo.get_by_id("inv1").status == InventoryStatus.FAILED


def test_start_aisle_processing_persists_starting_before_worker_launch() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    inv_repo = StubInventoryRepo([Inventory("inv1", "W", InventoryStatus.DRAFT, now, now)])
    aisle = Aisle("a1", "inv1", "A01", AisleStatus.CREATED, now, now)
    aisle_repo = StubAisleRepo()
    aisle_repo.save(aisle)
    job_repo = StubJobRepo()

    class InspectingLaunchService(WorkerLaunchService):
        def launch(self, job_id: str) -> str:
            persisted = job_repo.get_by_id(job_id)
            assert persisted is not None
            assert persisted.status == JobStatus.STARTING
            assert persisted.current_stage == "worker_launch"
            assert persisted.current_substep == "spawn_requested"
            assert persisted.execution_id is None
            return "exec-started"

    clock = FixedClock(now)
    reconciler = InventoryStatusReconciler(inv_repo, aisle_repo, clock)
    use_case = StartAisleProcessingUseCase(
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        job_repo=job_repo,
        launch_service=make_launch_service(
            aisle_repo=aisle_repo,
            job_repo=job_repo,
            worker_launch_service=InspectingLaunchService(),
            clock=clock,
            reconciler=reconciler,
        ),
        stale_reconciler=make_stale_reconciler(job_repo, clock),
    )

    job_id = use_case.execute(StartAisleProcessingCommand(inventory_id="inv1", aisle_id="a1"))
    saved_job = job_repo.get_by_id(job_id)
    assert saved_job is not None
    assert saved_job.execution_id == "exec-started"


def test_start_aisle_processing_reconciles_stale_active_job_before_new_launch() -> None:
    now = datetime(2025, 3, 6, 12, 15, 0, tzinfo=timezone.utc)
    stale_time = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    inv_repo = StubInventoryRepo([Inventory("inv1", "W", InventoryStatus.DRAFT, now, now)])
    aisle = Aisle("a1", "inv1", "A01", AisleStatus.CREATED, now, now)
    aisle_repo = StubAisleRepo()
    aisle_repo.save(aisle)
    job_repo = StubJobRepo()
    job_repo.save(
        Job(
            id="stale-job",
            target_type="aisle",
            target_id="a1",
            job_type="process_aisle",
            status=JobStatus.RUNNING,
            payload_json={"aisle_id": "a1"},
            created_at=stale_time,
            updated_at=stale_time,
            last_heartbeat_at=stale_time,
        )
    )
    queue = StubWorkerLaunchService()
    clock = FixedClock(now)
    reconciler = InventoryStatusReconciler(inv_repo, aisle_repo, clock)
    use_case = StartAisleProcessingUseCase(
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        job_repo=job_repo,
        launch_service=make_launch_service(
            aisle_repo=aisle_repo,
            job_repo=job_repo,
            worker_launch_service=queue,
            clock=clock,
            reconciler=reconciler,
        ),
        stale_reconciler=make_stale_reconciler(job_repo, clock, stale_after_seconds=60),
    )

    new_job_id = use_case.execute(StartAisleProcessingCommand(inventory_id="inv1", aisle_id="a1"))

    stale_job = job_repo.get_by_id("stale-job")
    assert stale_job is not None
    assert stale_job.status == JobStatus.FAILED
    assert stale_job.failure_code == STALE_FAILURE_CODE
    assert stale_job.failure_message == STALE_FAILURE_MESSAGE
    assert new_job_id in queue.launched


def test_start_aisle_processing_raises_inventory_not_found_when_resolve_execution_keys() -> None:
    """Phase 9: HTTP path resolves inventory before aisle checks."""
    inv_repo = StubInventoryRepo([])
    aisle_repo = StubAisleRepo()
    job_repo = StubJobRepo()
    queue = StubWorkerLaunchService()
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    reconciler = InventoryStatusReconciler(inv_repo, aisle_repo, FixedClock(now))
    use_case = StartAisleProcessingUseCase(
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        job_repo=job_repo,
        launch_service=make_launch_service(
            aisle_repo=aisle_repo,
            job_repo=job_repo,
            worker_launch_service=queue,
            clock=FixedClock(now),
            reconciler=reconciler,
        ),
        stale_reconciler=make_stale_reconciler(job_repo, FixedClock(now)),
    )
    with pytest.raises(InventoryNotFoundError):
        use_case.execute(
            StartAisleProcessingCommand(
                inventory_id="missing-inv",
                aisle_id="any-aisle",
                resolve_execution_keys=True,
            )
        )


def test_start_aisle_processing_raises_when_aisle_not_found() -> None:
    aisle_repo = StubAisleRepo()
    inv_repo = StubInventoryRepo([])
    job_repo = StubJobRepo()
    queue = StubWorkerLaunchService()
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    reconciler = InventoryStatusReconciler(inv_repo, aisle_repo, FixedClock(now))

    use_case = StartAisleProcessingUseCase(
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        job_repo=job_repo,
        launch_service=make_launch_service(
            aisle_repo=aisle_repo,
            job_repo=job_repo,
            worker_launch_service=queue,
            clock=FixedClock(now),
            reconciler=reconciler,
        ),
        stale_reconciler=make_stale_reconciler(job_repo, FixedClock(now)),
    )

    with pytest.raises(AisleNotFoundError):
        use_case.execute(StartAisleProcessingCommand(inventory_id="inv1", aisle_id="nonexistent"))


def test_start_aisle_processing_raises_when_aisle_belongs_to_other_inventory() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    aisle = Aisle("a1", "inv1", "A01", AisleStatus.CREATED, now, now)
    aisle_repo = StubAisleRepo()
    aisle_repo.save(aisle)
    inv_repo = StubInventoryRepo([])
    job_repo = StubJobRepo()
    queue = StubWorkerLaunchService()
    reconciler = InventoryStatusReconciler(inv_repo, aisle_repo, FixedClock(now))

    use_case = StartAisleProcessingUseCase(
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        job_repo=job_repo,
        launch_service=make_launch_service(
            aisle_repo=aisle_repo,
            job_repo=job_repo,
            worker_launch_service=queue,
            clock=FixedClock(now),
            reconciler=reconciler,
        ),
        stale_reconciler=make_stale_reconciler(job_repo, FixedClock(now)),
    )

    with pytest.raises(AisleNotFoundError):
        use_case.execute(StartAisleProcessingCommand(inventory_id="other-inv", aisle_id="a1"))


def test_start_aisle_processing_raises_when_active_job_exists() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    inv_repo = StubInventoryRepo([Inventory("inv1", "W", InventoryStatus.DRAFT, now, now)])
    aisle = Aisle("a1", "inv1", "A01", AisleStatus.QUEUED, now, now)
    aisle_repo = StubAisleRepo()
    aisle_repo.save(aisle)
    job_repo = StubJobRepo()
    job_repo.save(
        Job(
            id="existing",
            target_type="aisle",
            target_id="a1",
            job_type="process_aisle",
            status=JobStatus.QUEUED,
            payload_json={},
            created_at=now,
            updated_at=now,
        )
    )
    queue = StubWorkerLaunchService()
    reconciler = InventoryStatusReconciler(inv_repo, aisle_repo, FixedClock(now))

    use_case = StartAisleProcessingUseCase(
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        job_repo=job_repo,
        launch_service=make_launch_service(
            aisle_repo=aisle_repo,
            job_repo=job_repo,
            worker_launch_service=queue,
            clock=FixedClock(now),
            reconciler=reconciler,
        ),
        stale_reconciler=make_stale_reconciler(job_repo, FixedClock(now)),
    )

    with pytest.raises(ActiveJobExistsError):
        use_case.execute(StartAisleProcessingCommand(inventory_id="inv1", aisle_id="a1"))


def test_start_aisle_processing_allows_new_job_when_latest_is_terminal() -> None:
    """Non-blocking terminal latest job must not trip _require_no_active_process_job_for_aisle."""
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    inv_repo = StubInventoryRepo([Inventory("inv1", "W", InventoryStatus.DRAFT, now, now)])
    aisle = Aisle("a1", "inv1", "A01", AisleStatus.CREATED, now, now)
    aisle_repo = StubAisleRepo()
    aisle_repo.save(aisle)
    job_repo = StubJobRepo()
    job_repo.save(
        Job(
            id="old-done",
            target_type="aisle",
            target_id="a1",
            job_type="process_aisle",
            status=JobStatus.FAILED,
            payload_json={},
            created_at=now,
            updated_at=now,
        )
    )
    queue = StubWorkerLaunchService()
    clock = FixedClock(now)
    reconciler = InventoryStatusReconciler(inv_repo, aisle_repo, clock)

    use_case = StartAisleProcessingUseCase(
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        job_repo=job_repo,
        launch_service=make_launch_service(
            aisle_repo=aisle_repo,
            job_repo=job_repo,
            worker_launch_service=queue,
            clock=clock,
            reconciler=reconciler,
        ),
        stale_reconciler=make_stale_reconciler(job_repo, clock),
    )
    new_id = use_case.execute(StartAisleProcessingCommand(inventory_id="inv1", aisle_id="a1"))
    assert new_id != "old-done"
    assert queue.launched == [new_id]


def test_get_aisle_processing_status_returns_aisle_and_latest_job() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    aisle = Aisle("a1", "inv1", "A01", AisleStatus.QUEUED, now, now)
    job = Job(
        id="j1",
        target_type="aisle",
        target_id="a1",
        job_type="process_aisle",
        status=JobStatus.QUEUED,
        payload_json={"aisle_id": "a1"},
        created_at=now,
        updated_at=now,
    )
    aisle_repo = StubAisleRepo()
    aisle_repo.save(aisle)
    job_repo = StubJobRepo()
    job_repo.save(job)

    clock = FixedClock(now)
    use_case = GetAisleProcessingStatusUseCase(
        aisle_repo=aisle_repo,
        job_repo=job_repo,
        stale_reconciler=make_stale_reconciler(job_repo, clock),
    )
    result = use_case.execute("inv1", "a1")

    assert result.aisle.id == "a1"
    assert result.aisle.status == AisleStatus.QUEUED
    assert result.latest_job is not None
    assert result.latest_job.id == "j1"
    assert result.latest_job.status == JobStatus.QUEUED
    assert len(result.recent_jobs) == 1
    assert result.recent_jobs[0].id == "j1"


def test_get_aisle_processing_status_returns_none_job_when_no_job() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    aisle = Aisle("a1", "inv1", "A01", AisleStatus.CREATED, now, now)
    aisle_repo = StubAisleRepo()
    aisle_repo.save(aisle)
    job_repo = StubJobRepo()

    clock = FixedClock(now)
    use_case = GetAisleProcessingStatusUseCase(
        aisle_repo=aisle_repo,
        job_repo=job_repo,
        stale_reconciler=make_stale_reconciler(job_repo, clock),
    )
    result = use_case.execute("inv1", "a1")

    assert result.aisle.id == "a1"
    assert result.latest_job is None
    assert result.recent_jobs == ()


def test_get_aisle_processing_status_reconciles_stale_job() -> None:
    now = datetime(2025, 3, 6, 12, 15, 0, tzinfo=timezone.utc)
    stale_time = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    aisle = Aisle("a1", "inv1", "A01", AisleStatus.PROCESSING, stale_time, stale_time)
    job = Job(
        id="j-stale",
        target_type="aisle",
        target_id="a1",
        job_type="process_aisle",
        status=JobStatus.RUNNING,
        payload_json={"aisle_id": "a1"},
        created_at=stale_time,
        updated_at=stale_time,
        last_heartbeat_at=stale_time,
    )
    aisle_repo = StubAisleRepo()
    aisle_repo.save(aisle)
    job_repo = StubJobRepo()
    job_repo.save(job)
    clock = FixedClock(now)
    use_case = GetAisleProcessingStatusUseCase(
        aisle_repo=aisle_repo,
        job_repo=job_repo,
        stale_reconciler=make_stale_reconciler(job_repo, clock, stale_after_seconds=60),
    )

    result = use_case.execute("inv1", "a1")

    assert result.latest_job is not None
    assert result.latest_job.status == JobStatus.FAILED
    assert result.latest_job.failure_code == STALE_FAILURE_CODE


def test_get_aisle_processing_status_raises_when_aisle_not_found() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    aisle_repo = StubAisleRepo()
    job_repo = StubJobRepo()
    clock = FixedClock(now)
    use_case = GetAisleProcessingStatusUseCase(
        aisle_repo=aisle_repo,
        job_repo=job_repo,
        stale_reconciler=make_stale_reconciler(job_repo, clock),
    )

    with pytest.raises(AisleNotFoundError):
        use_case.execute("inv1", "nonexistent")
