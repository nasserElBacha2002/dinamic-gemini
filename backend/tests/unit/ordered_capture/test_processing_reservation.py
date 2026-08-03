"""Unit tests — ordered-capture processing reservation (memory UoW)."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from src.application.errors import WorkerLaunchFailedError
from src.application.ports.services import WorkerLaunchService
from src.application.services.aisle_job_launch_service import AisleJobLaunchService
from src.application.services.inventory_status_reconciler import InventoryStatusReconciler
from src.application.services.job_stale_reconciler import JobStaleReconciler
from src.application.services.ordered_capture_processing_reservation import (
    OrderedCaptureProcessingReservationService,
)
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
from src.infrastructure.persistence.memory_ordered_capture_processing_reservation_unit_of_work import (
    build_memory_ordered_capture_processing_reservation_uow_factory,
)
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


class _OkWorker(WorkerLaunchService):
    def launch(self, job_id: str) -> str:
        return f"exec-{job_id}"


class _FailingWorker(WorkerLaunchService):
    def launch(self, job_id: str) -> str:
        raise RuntimeError("spawn denied")


def _reservation_service(job_repo, session_repo) -> OrderedCaptureProcessingReservationService:
    return OrderedCaptureProcessingReservationService(
        uow_factory=build_memory_ordered_capture_processing_reservation_uow_factory(
            job_repo=job_repo,
            session_repo=session_repo,
        )
    )


def _sealed_fixture(*, worker: WorkerLaunchService | None = None):
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
    launch_worker = worker or _OkWorker()
    reconciler = InventoryStatusReconciler(inv_repo, aisle_repo, clock)
    launch = AisleJobLaunchService(
        aisle_repo=aisle_repo,
        job_repo=job_repo,
        worker_launch_service=launch_worker,
        clock=clock,
        status_reconciler=reconciler,
    )
    reservation = _reservation_service(job_repo, session_repo)
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
        ordered_processing_reservation=reservation,
    )
    cmd = StartAisleProcessingCommand(
        inventory_id="inv-1",
        aisle_id="aisle-1",
        principal=principal,
        ordered_capture_session_id=session.id,
    )
    return use_case, cmd, session_repo, job_repo, reservation, sealed, now


def test_memory_double_reserve_same_job_and_processing_link() -> None:
    _use_case, _cmd, session_repo, job_repo, reservation, sealed, now = _sealed_fixture()
    template_a = Job(
        id=str(uuid4()),
        target_type="aisle",
        target_id="aisle-1",
        job_type="process_aisle",
        status=JobStatus.STARTING,
        payload_json={
            "aisle_id": "aisle-1",
            "ordered_capture_session_id": sealed.id,
            "sequence_version": 1,
        },
        created_at=now,
        updated_at=now,
        started_at=now,
        ordered_capture_session_id=sealed.id,
        sequence_version=1,
    )
    template_b = Job(
        id=str(uuid4()),
        target_type="aisle",
        target_id="aisle-1",
        job_type="process_aisle",
        status=JobStatus.STARTING,
        payload_json={
            "aisle_id": "aisle-1",
            "ordered_capture_session_id": sealed.id,
            "sequence_version": 1,
        },
        created_at=now,
        updated_at=now,
        started_at=now,
        ordered_capture_session_id=sealed.id,
        sequence_version=1,
    )
    first = reservation.reserve(template_a, sealed, now)
    second = reservation.reserve(template_b, sealed, now)
    assert first.created is True
    assert second.created is False
    assert first.job.id == second.job.id == template_a.id
    refreshed = session_repo.get_by_id(sealed.id)
    assert refreshed is not None
    assert refreshed.status == OrderedCaptureSessionStatus.PROCESSING
    assert refreshed.processing_job_id == first.job.id
    assert job_repo.get_by_id(first.job.id) is not None


def test_launch_failure_leaves_session_processing() -> None:
    use_case, cmd, session_repo, _job_repo, _reservation, sealed, _now = _sealed_fixture(
        worker=_FailingWorker()
    )
    with pytest.raises(WorkerLaunchFailedError):
        use_case.execute(cmd)
    refreshed = session_repo.get_by_id(sealed.id)
    assert refreshed is not None
    assert refreshed.status == OrderedCaptureSessionStatus.PROCESSING
    assert refreshed.processing_job_id is not None
