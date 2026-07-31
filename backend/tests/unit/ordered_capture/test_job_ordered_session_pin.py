"""Unit tests — ordered-session job pin (create_or_get + start idempotency)."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from src.application.ports.services import WorkerLaunchService
from src.application.services.aisle_job_launch_service import AisleJobLaunchService
from src.application.services.ordered_capture_processing_reservation import (
    OrderedCaptureProcessingReservationService,
)
from src.infrastructure.persistence.memory_ordered_capture_processing_reservation_unit_of_work import (
    build_memory_ordered_capture_processing_reservation_uow_factory,
)
from src.application.services.inventory_status_reconciler import InventoryStatusReconciler
from src.application.services.job_stale_reconciler import JobStaleReconciler
from src.application.use_cases.aisles.start_aisle_processing import (
    StartAisleProcessingCommand,
    StartAisleProcessingUseCase,
)
from src.application.use_cases.ordered_capture.manage_ordered_capture_session import (
    CreateOrderedCaptureSessionCommand,
    CreateOrderedCaptureSessionUseCase,
    SealOrderedCaptureSessionCommand,
    SealOrderedCaptureSessionUseCase,
)
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.assets.entities import SourceAsset, SourceAssetType
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.domain.jobs.entities import Job, JobStatus
from src.domain.ordered_capture.entities import OrderedCaptureSessionStatus
from src.infrastructure.repositories.memory_aisle_repository import MemoryAisleRepository
from src.infrastructure.repositories.memory_inventory_repository import (
    MemoryInventoryRepository,
)
from src.infrastructure.repositories.memory_job_repository import MemoryJobRepository
from src.infrastructure.repositories.memory_ordered_capture_session_repository import (
    MemoryOrderedCaptureSessionRepository,
)
from src.infrastructure.repositories.memory_source_asset_repository import (
    MemorySourceAssetRepository,
)
from tests.support.access_principal_helpers import platform_principal, policy_for


class _FixedClock:
    def now(self) -> datetime:
        return datetime(2026, 7, 17, tzinfo=timezone.utc)


class _CountingWorkerLaunch(WorkerLaunchService):
    def __init__(self) -> None:
        self.launch_calls = 0

    def launch(self, job_id: str) -> str:
        self.launch_calls += 1
        return f"exec-{job_id}"


def _base_fixture():
    now = datetime(2026, 7, 17, tzinfo=timezone.utc)
    inv = Inventory(
        id="inv-1",
        name="Inv",
        status=InventoryStatus.DRAFT,
        created_at=now,
        updated_at=now,
        client_id="client-1",
    )
    aisle = Aisle(
        id="aisle-1",
        inventory_id="inv-1",
        code="A1",
        status=AisleStatus.CREATED,
        created_at=now,
        updated_at=now,
        is_active=True,
    )
    inv_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    inv_repo.save(inv)
    aisle_repo.save(aisle)
    session_repo = MemoryOrderedCaptureSessionRepository()
    asset_repo = MemorySourceAssetRepository()
    job_repo = MemoryJobRepository()
    clock = _FixedClock()
    access = policy_for(inv_repo, aisle_repo)
    return (
        inv_repo,
        aisle_repo,
        session_repo,
        asset_repo,
        job_repo,
        clock,
        access,
        aisle,
        now,
    )


def test_create_or_get_returns_same_job_id_for_double_call() -> None:
    job_repo = MemoryJobRepository()
    now = datetime(2026, 7, 17, tzinfo=timezone.utc)
    first = Job(
        id=str(uuid4()),
        target_type="aisle",
        target_id="aisle-1",
        job_type="process_aisle",
        status=JobStatus.STARTING,
        payload_json={"aisle_id": "aisle-1"},
        created_at=now,
        updated_at=now,
        ordered_capture_session_id="sess-1",
        sequence_version=1,
    )
    second = Job(
        id=str(uuid4()),
        target_type="aisle",
        target_id="aisle-1",
        job_type="process_aisle",
        status=JobStatus.STARTING,
        payload_json={"aisle_id": "aisle-1"},
        created_at=now,
        updated_at=now,
        ordered_capture_session_id="sess-1",
        sequence_version=1,
    )
    job_a, created_a = job_repo.create_or_get_for_ordered_session(first)
    job_b, created_b = job_repo.create_or_get_for_ordered_session(second)
    assert created_a is True
    assert created_b is False
    assert job_a.id == job_b.id == first.id
    assert job_a.ordered_capture_session_id == "sess-1"
    assert job_a.sequence_version == 1


def test_memory_job_repo_persists_ordered_session_fields() -> None:
    job_repo = MemoryJobRepository()
    now = datetime(2026, 7, 17, tzinfo=timezone.utc)
    job = Job(
        id=str(uuid4()),
        target_type="aisle",
        target_id="aisle-1",
        job_type="process_aisle",
        status=JobStatus.STARTING,
        payload_json={"aisle_id": "aisle-1"},
        created_at=now,
        updated_at=now,
        ordered_capture_session_id="sess-persist",
        sequence_version=3,
    )
    job_repo.save(job)
    loaded = job_repo.get_by_id(job.id)
    assert loaded is not None
    assert loaded.ordered_capture_session_id == "sess-persist"
    assert loaded.sequence_version == 3
    by_session = job_repo.get_by_ordered_capture_session(
        "sess-persist", sequence_version=3
    )
    assert by_session is not None
    assert by_session.id == job.id


def test_memory_save_rejects_duplicate_ordered_session_version() -> None:
    job_repo = MemoryJobRepository()
    now = datetime(2026, 7, 17, tzinfo=timezone.utc)
    job_repo.save(
        Job(
            id="job-1",
            target_type="aisle",
            target_id="aisle-1",
            job_type="process_aisle",
            status=JobStatus.STARTING,
            payload_json={"aisle_id": "aisle-1"},
            created_at=now,
            updated_at=now,
            ordered_capture_session_id="sess-dup",
            sequence_version=1,
        )
    )
    try:
        job_repo.save(
            Job(
                id="job-2",
                target_type="aisle",
                target_id="aisle-1",
                job_type="process_aisle",
                status=JobStatus.STARTING,
                payload_json={"aisle_id": "aisle-1"},
                created_at=now,
                updated_at=now,
                ordered_capture_session_id="sess-dup",
                sequence_version=1,
            )
        )
        raise AssertionError("expected unique violation ValueError")
    except ValueError as exc:
        assert "UQ_inventory_jobs_ordered_session_version" in str(exc)


def test_start_processing_idempotent_via_columns_without_payload_scan() -> None:
    (
        inv_repo,
        aisle_repo,
        session_repo,
        asset_repo,
        job_repo,
        clock,
        access,
        aisle,
        now,
    ) = _base_fixture()
    principal = platform_principal()
    create = CreateOrderedCaptureSessionUseCase(
        session_repo=session_repo,
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        access_policy=access,
        clock=clock,
    )
    seal = SealOrderedCaptureSessionUseCase(
        session_repo=session_repo,
        asset_repo=asset_repo,
        access_policy=access,
        clock=clock,
    )
    session = create.execute(
        CreateOrderedCaptureSessionCommand(
            inventory_id="inv-1", aisle_id="aisle-1", principal=principal
        )
    )
    for n in range(1, 3):
        asset_repo.save(
            SourceAsset(
                id=str(uuid4()),
                aisle_id="aisle-1",
                type=SourceAssetType.PHOTO,
                original_filename=f"{n}.jpg",
                storage_path=f"/t/{n}.jpg",
                mime_type="image/jpeg",
                uploaded_at=now,
                upload_client_file_id=str(uuid4()),
                ordered_capture_session_id=session.id,
                sequence_number=n,
                sequence_source="CLIENT_ASSIGNED",
            )
        )
    sealed = seal.execute(
        SealOrderedCaptureSessionCommand(
            session_id=session.id,
            expected_asset_count=2,
            sequence_version=1,
            principal=principal,
        )
    )
    assert sealed.status == OrderedCaptureSessionStatus.SEALED

    worker = _CountingWorkerLaunch()
    reconciler = InventoryStatusReconciler(inv_repo, aisle_repo, clock)
    launch = AisleJobLaunchService(
        aisle_repo=aisle_repo,
        job_repo=job_repo,
        worker_launch_service=worker,
        clock=clock,
        status_reconciler=reconciler,
    )
    use_case = StartAisleProcessingUseCase(
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        asset_repo=asset_repo,
        job_repo=job_repo,
        launch_service=launch,
        stale_reconciler=JobStaleReconciler(
            job_repo=job_repo, clock=clock, stale_after_seconds=900, aisle_repo=aisle_repo
        ),
        access_policy=access,
        ordered_session_repo=session_repo,
        ordered_processing_reservation=OrderedCaptureProcessingReservationService(
            uow_factory=build_memory_ordered_capture_processing_reservation_uow_factory(
                job_repo=job_repo,
                session_repo=session_repo,
            )
        ),
    )
    cmd = StartAisleProcessingCommand(
        inventory_id="inv-1",
        aisle_id="aisle-1",
        principal=principal,
        ordered_capture_session_id=session.id,
    )
    first = use_case.execute(cmd)
    # Reset session to SEALED to exercise column lookup path (concurrent-style replay)
    # after job row exists; ActiveJobExists would otherwise block a fresh start.
    refreshed = session_repo.get_by_id(session.id)
    assert refreshed is not None
    assert refreshed.status == OrderedCaptureSessionStatus.PROCESSING
    refreshed.status = OrderedCaptureSessionStatus.SEALED
    session_repo.save(refreshed)

    second = use_case.execute(cmd)
    assert first.job_id == second.job_id
    assert worker.launch_calls == 1
    pinned = job_repo.get_by_ordered_capture_session(
        session.id, sequence_version=1
    )
    assert pinned is not None
    assert pinned.id == first.job_id
    assert pinned.ordered_capture_session_id == session.id
    assert pinned.sequence_version == 1
    # Payload scan not required — pin lives on job columns.
    assert (pinned.payload_json or {}).get("ordered_capture_session_id") == session.id
