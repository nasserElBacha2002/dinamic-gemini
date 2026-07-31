"""Unit tests — StartAisleProcessing idempotent when session is already PROCESSING."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from src.application.errors import ProcessingRejectedUnsealedSessionError
from src.application.ports.services import WorkerLaunchService
from src.application.services.aisle_job_launch_service import AisleJobLaunchService
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


def _fixture():
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
    )
    cmd = StartAisleProcessingCommand(
        inventory_id="inv-1",
        aisle_id="aisle-1",
        principal=principal,
        ordered_capture_session_id=session.id,
    )
    return use_case, cmd, session_repo, session, worker


def test_start_processing_processing_status_idempotent() -> None:
    use_case, cmd, session_repo, session, worker = _fixture()
    first = use_case.execute(cmd)
    refreshed = session_repo.get_by_id(session.id)
    assert refreshed is not None
    assert refreshed.status == OrderedCaptureSessionStatus.PROCESSING

    second = use_case.execute(cmd)
    assert second.job_id == first.job_id
    assert worker.launch_calls == 1


def test_start_processing_completed_with_existing_job_returns_same_id() -> None:
    use_case, cmd, session_repo, session, worker = _fixture()
    first = use_case.execute(cmd)
    refreshed = session_repo.get_by_id(session.id)
    assert refreshed is not None
    refreshed.status = OrderedCaptureSessionStatus.COMPLETED
    refreshed.completed_at = datetime(2026, 7, 18, tzinfo=timezone.utc)
    session_repo.save(refreshed)

    second = use_case.execute(cmd)
    assert second.job_id == first.job_id
    assert worker.launch_calls == 1


def test_start_processing_failed_without_job_rejects() -> None:
    use_case, cmd, session_repo, session, _worker = _fixture()
    refreshed = session_repo.get_by_id(session.id)
    assert refreshed is not None
    refreshed.status = OrderedCaptureSessionStatus.FAILED
    refreshed.completed_at = datetime(2026, 7, 18, tzinfo=timezone.utc)
    session_repo.save(refreshed)

    with pytest.raises(ProcessingRejectedUnsealedSessionError) as exc_info:
        use_case.execute(cmd)
    assert "FAILED" in str(exc_info.value)
