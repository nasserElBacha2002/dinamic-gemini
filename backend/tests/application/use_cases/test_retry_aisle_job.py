from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Optional, Sequence

import pytest

from src.application.errors import AisleNotFoundError, ActiveJobExistsError
from src.application.ports.repositories import AisleRepository, InventoryRepository, JobRepository
from src.application.ports.services import WorkerLaunchService
from src.application.services.aisle_job_launch_service import AisleJobLaunchService
from src.application.services.inventory_status_reconciler import InventoryStatusReconciler
from src.application.services.job_stale_reconciler import JobStaleReconciler
from src.application.use_cases.retry_aisle_job import RetryAisleJobCommand, RetryAisleJobUseCase
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.domain.jobs.entities import Job, JobStatus


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
        for aisle in self._store.values():
            if aisle.inventory_id == inventory_id and aisle.code == code:
                return aisle
        return None


class StubJobRepo(JobRepository):
    def __init__(self) -> None:
        self._store: Dict[str, Job] = {}

    def save(self, job: Job) -> None:
        self._store[job.id] = job

    def get_by_id(self, job_id: str) -> Optional[Job]:
        return self._store.get(job_id)

    def get_latest_by_target(self, target_type: str, target_id: str) -> Optional[Job]:
        matches = [
            job for job in self._store.values()
            if job.target_type == target_type and job.target_id == target_id
        ]
        if not matches:
            return None
        matches.sort(key=lambda job: (job.updated_at, job.created_at), reverse=True)
        return matches[0]

    def get_latest_by_targets(self, target_type: str, target_ids: Sequence[str]) -> Dict[str, Job]:
        return {
            target_id: latest
            for target_id in target_ids
            if (latest := self.get_latest_by_target(target_type, target_id)) is not None
        }

    def list_jobs_for_target(
        self, target_type: str, target_id: str, *, limit: int = 50
    ) -> Sequence[Job]:
        candidates = [
            job
            for job in self._store.values()
            if job.target_type == target_type and job.target_id == target_id
        ]
        candidates.sort(key=lambda job: (job.updated_at, job.created_at), reverse=True)
        n = max(1, int(limit))
        return candidates[:n]


class StubWorkerLaunchService(WorkerLaunchService):
    def __init__(self) -> None:
        self.launched: list[str] = []

    def launch(self, job_id: str) -> str:
        self.launched.append(job_id)
        return f"exec-{job_id}"


def make_stale_reconciler(job_repo: JobRepository, clock: FixedClock) -> JobStaleReconciler:
    return JobStaleReconciler(job_repo=job_repo, clock=clock, stale_after_seconds=900)


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


def _base_context() -> tuple[datetime, StubInventoryRepo, StubAisleRepo, StubJobRepo, FixedClock]:
    now = datetime(2026, 3, 31, 12, 0, 0, tzinfo=timezone.utc)
    inv_repo = StubInventoryRepo([Inventory("inv-1", "Inventory", InventoryStatus.DRAFT, now, now)])
    aisle_repo = StubAisleRepo()
    aisle_repo.save(Aisle("aisle-1", "inv-1", "A01", AisleStatus.FAILED, now, now))
    return now, inv_repo, aisle_repo, StubJobRepo(), FixedClock(now)


def test_retry_failed_job_creates_new_attempt_with_lineage() -> None:
    now, inv_repo, aisle_repo, job_repo, clock = _base_context()
    original = Job(
        id="job-failed",
        target_type="aisle",
        target_id="aisle-1",
        job_type="process_aisle",
        status=JobStatus.FAILED,
        payload_json={"aisle_id": "aisle-1"},
        created_at=now,
        updated_at=now,
        attempt_count=1,
        failure_code="PROCESSING_FAILED",
        provider_name="fake",
        model_name="fixture",
        prompt_key="global_v21",
    )
    job_repo.save(original)
    launcher = StubWorkerLaunchService()
    reconciler = InventoryStatusReconciler(inv_repo, aisle_repo, clock)
    use_case = RetryAisleJobUseCase(
        aisle_repo=aisle_repo,
        job_repo=job_repo,
        launch_service=make_launch_service(
            aisle_repo=aisle_repo,
            job_repo=job_repo,
            worker_launch_service=launcher,
            clock=clock,
            reconciler=reconciler,
        ),
        stale_reconciler=make_stale_reconciler(job_repo, clock),
    )

    retried = use_case.execute(RetryAisleJobCommand("inv-1", "aisle-1", "job-failed"))

    assert retried.id != original.id
    assert retried.retry_of_job_id == "job-failed"  # immediate previous attempt
    assert retried.attempt_count == 2
    assert retried.status == JobStatus.STARTING
    assert retried.execution_id == f"exec-{retried.id}"
    assert retried.provider_name == "fake"
    assert retried.model_name == "fixture"
    assert retried.prompt_key == "global_v21"
    assert launcher.launched == [retried.id]
    assert job_repo.get_by_id("job-failed").status == JobStatus.FAILED


def test_retry_canceled_job_creates_new_attempt() -> None:
    now, inv_repo, aisle_repo, job_repo, clock = _base_context()
    original = Job(
        id="job-canceled",
        target_type="aisle",
        target_id="aisle-1",
        job_type="process_aisle",
        status=JobStatus.CANCELED,
        payload_json={"aisle_id": "aisle-1"},
        created_at=now,
        updated_at=now,
        attempt_count=2,
    )
    job_repo.save(original)
    launcher = StubWorkerLaunchService()
    reconciler = InventoryStatusReconciler(inv_repo, aisle_repo, clock)
    use_case = RetryAisleJobUseCase(
        aisle_repo=aisle_repo,
        job_repo=job_repo,
        launch_service=make_launch_service(
            aisle_repo=aisle_repo,
            job_repo=job_repo,
            worker_launch_service=launcher,
            clock=clock,
            reconciler=reconciler,
        ),
        stale_reconciler=make_stale_reconciler(job_repo, clock),
    )

    retried = use_case.execute(RetryAisleJobCommand("inv-1", "aisle-1", "job-canceled"))

    assert retried.retry_of_job_id == "job-canceled"
    assert retried.attempt_count == 3
    assert launcher.launched == [retried.id]


def test_retry_of_retry_creates_linear_chain_with_immediate_previous_link() -> None:
    now, inv_repo, aisle_repo, job_repo, clock = _base_context()
    original = Job(
        id="job-original",
        target_type="aisle",
        target_id="aisle-1",
        job_type="process_aisle",
        status=JobStatus.FAILED,
        payload_json={"aisle_id": "aisle-1"},
        created_at=now,
        updated_at=now,
        attempt_count=1,
    )
    retry_one_time = datetime(2026, 3, 31, 12, 1, 0, tzinfo=timezone.utc)
    retry_one = Job(
        id="job-retry-1",
        target_type="aisle",
        target_id="aisle-1",
        job_type="process_aisle",
        status=JobStatus.CANCELED,
        payload_json={"aisle_id": "aisle-1"},
        created_at=retry_one_time,
        updated_at=retry_one_time,
        attempt_count=2,
        retry_of_job_id="job-original",
    )
    job_repo.save(original)
    job_repo.save(retry_one)
    launcher = StubWorkerLaunchService()
    reconciler = InventoryStatusReconciler(inv_repo, aisle_repo, clock)
    use_case = RetryAisleJobUseCase(
        aisle_repo=aisle_repo,
        job_repo=job_repo,
        launch_service=make_launch_service(
            aisle_repo=aisle_repo,
            job_repo=job_repo,
            worker_launch_service=launcher,
            clock=clock,
            reconciler=reconciler,
        ),
        stale_reconciler=make_stale_reconciler(job_repo, clock),
    )

    retried = use_case.execute(RetryAisleJobCommand("inv-1", "aisle-1", "job-retry-1"))

    assert retried.retry_of_job_id == "job-retry-1"
    assert retried.attempt_count == 3
    assert launcher.launched == [retried.id]


@pytest.mark.parametrize(
    "status",
    [
        JobStatus.QUEUED,
        JobStatus.STARTING,
        JobStatus.RUNNING,
        JobStatus.CANCEL_REQUESTED,
        JobStatus.SUCCEEDED,
    ],
)
def test_retry_ineligible_status_raises_conflict(status: JobStatus) -> None:
    now, inv_repo, aisle_repo, job_repo, clock = _base_context()
    job_repo.save(
        Job(
            id="job-1",
            target_type="aisle",
            target_id="aisle-1",
            job_type="process_aisle",
            status=status,
            payload_json={"aisle_id": "aisle-1"},
            created_at=now,
            updated_at=now,
        )
    )
    use_case = RetryAisleJobUseCase(
        aisle_repo=aisle_repo,
        job_repo=job_repo,
        launch_service=make_launch_service(
            aisle_repo=aisle_repo,
            job_repo=job_repo,
            worker_launch_service=StubWorkerLaunchService(),
            clock=clock,
            reconciler=InventoryStatusReconciler(inv_repo, aisle_repo, clock),
        ),
        stale_reconciler=make_stale_reconciler(job_repo, clock),
    )

    with pytest.raises(ValueError, match="Cannot retry"):
        use_case.execute(RetryAisleJobCommand("inv-1", "aisle-1", "job-1"))


def test_retry_is_blocked_when_active_job_exists() -> None:
    now, inv_repo, aisle_repo, job_repo, clock = _base_context()
    job_repo.save(
        Job(
            id="job-old-failed",
            target_type="aisle",
            target_id="aisle-1",
            job_type="process_aisle",
            status=JobStatus.FAILED,
            payload_json={"aisle_id": "aisle-1"},
            created_at=now,
            updated_at=now,
            attempt_count=1,
        )
    )
    later = datetime(2026, 3, 31, 12, 5, 0, tzinfo=timezone.utc)
    job_repo.save(
        Job(
            id="job-active",
            target_type="aisle",
            target_id="aisle-1",
            job_type="process_aisle",
            status=JobStatus.RUNNING,
            payload_json={"aisle_id": "aisle-1"},
            created_at=later,
            updated_at=later,
            attempt_count=2,
        )
    )
    use_case = RetryAisleJobUseCase(
        aisle_repo=aisle_repo,
        job_repo=job_repo,
        launch_service=make_launch_service(
            aisle_repo=aisle_repo,
            job_repo=job_repo,
            worker_launch_service=StubWorkerLaunchService(),
            clock=clock,
            reconciler=InventoryStatusReconciler(inv_repo, aisle_repo, clock),
        ),
        stale_reconciler=make_stale_reconciler(job_repo, clock),
    )

    with pytest.raises(ActiveJobExistsError):
        use_case.execute(RetryAisleJobCommand("inv-1", "aisle-1", "job-old-failed"))


def test_retry_of_older_terminal_attempt_is_rejected_when_newer_terminal_exists() -> None:
    now, inv_repo, aisle_repo, job_repo, clock = _base_context()
    older = Job(
        id="job-failed-old",
        target_type="aisle",
        target_id="aisle-1",
        job_type="process_aisle",
        status=JobStatus.FAILED,
        payload_json={"aisle_id": "aisle-1"},
        created_at=now,
        updated_at=now,
        attempt_count=1,
    )
    newer_time = datetime(2026, 3, 31, 12, 5, 0, tzinfo=timezone.utc)
    newer = Job(
        id="job-failed-newer",
        target_type="aisle",
        target_id="aisle-1",
        job_type="process_aisle",
        status=JobStatus.CANCELED,
        payload_json={"aisle_id": "aisle-1"},
        created_at=newer_time,
        updated_at=newer_time,
        attempt_count=2,
        retry_of_job_id="job-failed-old",
    )
    job_repo.save(older)
    job_repo.save(newer)
    use_case = RetryAisleJobUseCase(
        aisle_repo=aisle_repo,
        job_repo=job_repo,
        launch_service=make_launch_service(
            aisle_repo=aisle_repo,
            job_repo=job_repo,
            worker_launch_service=StubWorkerLaunchService(),
            clock=clock,
            reconciler=InventoryStatusReconciler(inv_repo, aisle_repo, clock),
        ),
        stale_reconciler=make_stale_reconciler(job_repo, clock),
    )

    with pytest.raises(ValueError, match="latest retryable terminal attempt is job-failed-newer"):
        use_case.execute(RetryAisleJobCommand("inv-1", "aisle-1", "job-failed-old"))


def test_retry_launch_failure_marks_new_retry_job_failed_only() -> None:
    now, inv_repo, aisle_repo, job_repo, clock = _base_context()
    original = Job(
        id="job-failed",
        target_type="aisle",
        target_id="aisle-1",
        job_type="process_aisle",
        status=JobStatus.FAILED,
        payload_json={"aisle_id": "aisle-1"},
        created_at=now,
        updated_at=now,
        attempt_count=1,
    )
    job_repo.save(original)

    class FailingLaunchService(WorkerLaunchService):
        def launch(self, job_id: str) -> str:
            raise RuntimeError("spawn failed")

    use_case = RetryAisleJobUseCase(
        aisle_repo=aisle_repo,
        job_repo=job_repo,
        launch_service=make_launch_service(
            aisle_repo=aisle_repo,
            job_repo=job_repo,
            worker_launch_service=FailingLaunchService(),
            clock=clock,
            reconciler=InventoryStatusReconciler(inv_repo, aisle_repo, clock),
        ),
        stale_reconciler=make_stale_reconciler(job_repo, clock),
    )

    with pytest.raises(RuntimeError, match="spawn failed"):
        use_case.execute(RetryAisleJobCommand("inv-1", "aisle-1", "job-failed"))

    retry_jobs = [job for job in job_repo._store.values() if job.retry_of_job_id == "job-failed"]
    assert len(retry_jobs) == 1
    assert retry_jobs[0].status == JobStatus.FAILED
    assert retry_jobs[0].failure_code == "WORKER_LAUNCH_FAILED"
    assert job_repo.get_by_id("job-failed").status == JobStatus.FAILED


def test_retry_job_not_found_raises_not_found() -> None:
    _, inv_repo, aisle_repo, job_repo, clock = _base_context()
    use_case = RetryAisleJobUseCase(
        aisle_repo=aisle_repo,
        job_repo=job_repo,
        launch_service=make_launch_service(
            aisle_repo=aisle_repo,
            job_repo=job_repo,
            worker_launch_service=StubWorkerLaunchService(),
            clock=clock,
            reconciler=InventoryStatusReconciler(inv_repo, aisle_repo, clock),
        ),
        stale_reconciler=make_stale_reconciler(job_repo, clock),
    )

    with pytest.raises(AisleNotFoundError):
        use_case.execute(RetryAisleJobCommand("inv-1", "aisle-1", "missing-job"))
