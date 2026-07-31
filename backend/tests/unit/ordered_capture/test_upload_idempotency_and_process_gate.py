"""Unit tests — ordered upload idempotency + process rejects UPLOADING sessions."""

from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from uuid import uuid4

import pytest

from src.application.dto.uploaded_file import UploadedFile
from src.application.errors import ProcessingRejectedUnsealedSessionError
from src.application.ports.services import WorkerLaunchService
from src.application.services.aisle_job_launch_service import AisleJobLaunchService
from src.application.services.inventory_status_reconciler import InventoryStatusReconciler
from src.application.services.job_stale_reconciler import JobStaleReconciler
from src.application.use_cases.aisles.start_aisle_processing import (
    StartAisleProcessingCommand,
    StartAisleProcessingUseCase,
)
from src.application.use_cases.aisles.upload_aisle_assets import UploadAisleAssetsUseCase
from src.application.use_cases.ordered_capture.manage_ordered_capture_session import (
    CreateOrderedCaptureSessionCommand,
    CreateOrderedCaptureSessionUseCase,
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
from src.infrastructure.storage.artifact_store import StoredArtifact
from tests.support.access_principal_helpers import platform_principal, policy_for


class _FixedClock:
    def now(self) -> datetime:
        return datetime(2026, 7, 17, tzinfo=timezone.utc)


class _StubArtifactStorage:
    def save_file(self, path: str, file_obj: BytesIO, content_type: str) -> str:
        return path

    def put_object(self, path: str, file_obj: BytesIO, content_type: str) -> StoredArtifact:
        content = file_obj.read()
        return StoredArtifact(
            storage_provider="s3",
            storage_bucket="bucket-a",
            storage_key=path,
            content_type=content_type,
            file_size_bytes=len(content),
            etag="etag-test",
        )

    def delete_file(self, path: str) -> None:
        return None


class _StubWorkerLaunch(WorkerLaunchService):
    def launch(self, job_id: str) -> str:
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
    clock = _FixedClock()
    access = policy_for(inv_repo, aisle_repo)
    create = CreateOrderedCaptureSessionUseCase(
        session_repo=session_repo,
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        access_policy=access,
        clock=clock,
    )
    upload = UploadAisleAssetsUseCase(
        aisle_repo=aisle_repo,
        asset_repo=asset_repo,
        artifact_storage=_StubArtifactStorage(),  # type: ignore[arg-type]
        clock=clock,
        status_reconciler=InventoryStatusReconciler(inv_repo, aisle_repo, clock),
        access_policy=access,
        ordered_session_repo=session_repo,
    )
    return create, upload, session_repo, asset_repo, inv_repo, aisle_repo, clock, access


def test_ordered_upload_idempotent_by_session_and_client_image_id() -> None:
    create, upload, session_repo, asset_repo, *_rest = _fixture()
    principal = platform_principal()
    session = create.execute(
        CreateOrderedCaptureSessionCommand(
            inventory_id="inv-1", aisle_id="aisle-1", principal=principal
        )
    )
    client_image_id = str(uuid4())
    payload = b"fake-jpeg-bytes"
    files = [
        UploadedFile(
            "1.jpg",
            BytesIO(payload),
            "image/jpeg",
            client_file_id=client_image_id,
            upload_batch_id="batch-ordered-1",
            ordered_capture_session_id=session.id,
            sequence_number=1,
        )
    ]
    first = upload.execute("inv-1", "aisle-1", files, principal=principal)
    assert len(first.assets) == 1
    assert first.errors == []
    first_id = first.assets[0].id
    assert (first.assets[0].metadata_json or {}).get("content_sha256")

    # Replay with same content fingerprint (same bytes).
    replay_files = [
        UploadedFile(
            "1.jpg",
            BytesIO(payload),
            "image/jpeg",
            client_file_id=client_image_id,
            upload_batch_id="batch-ordered-1",
            ordered_capture_session_id=session.id,
            sequence_number=1,
        )
    ]
    second = upload.execute("inv-1", "aisle-1", replay_files, principal=principal)
    assert len(second.assets) == 1
    assert second.errors == []
    assert second.assets[0].id == first_id
    assert len(list(asset_repo.list_by_aisle("aisle-1"))) == 1
    refreshed = session_repo.get_by_id(session.id)
    assert refreshed is not None
    assert refreshed.status == OrderedCaptureSessionStatus.UPLOADING


def test_ordered_upload_same_key_different_sequence_conflicts() -> None:
    create, upload, _session_repo, asset_repo, *_rest = _fixture()
    principal = platform_principal()
    session = create.execute(
        CreateOrderedCaptureSessionCommand(
            inventory_id="inv-1", aisle_id="aisle-1", principal=principal
        )
    )
    client_image_id = str(uuid4())
    payload = b"fake-jpeg-bytes"
    first = upload.execute(
        "inv-1",
        "aisle-1",
        [
            UploadedFile(
                "1.jpg",
                BytesIO(payload),
                "image/jpeg",
                client_file_id=client_image_id,
                upload_batch_id="batch-ordered-1",
                ordered_capture_session_id=session.id,
                sequence_number=1,
            )
        ],
        principal=principal,
    )
    assert len(first.assets) == 1
    assert first.errors == []

    second = upload.execute(
        "inv-1",
        "aisle-1",
        [
            UploadedFile(
                "1.jpg",
                BytesIO(payload),
                "image/jpeg",
                client_file_id=client_image_id,
                upload_batch_id="batch-ordered-1",
                ordered_capture_session_id=session.id,
                sequence_number=2,
            )
        ],
        principal=principal,
    )
    assert second.assets == []
    assert len(second.errors) == 1
    assert second.errors[0].code == "IDEMPOTENCY_KEY_REUSED"
    assert len(list(asset_repo.list_by_aisle("aisle-1"))) == 1


def test_ordered_upload_same_key_different_fingerprint_conflicts() -> None:
    create, upload, _session_repo, asset_repo, *_rest = _fixture()
    principal = platform_principal()
    session = create.execute(
        CreateOrderedCaptureSessionCommand(
            inventory_id="inv-1", aisle_id="aisle-1", principal=principal
        )
    )
    client_image_id = str(uuid4())
    first = upload.execute(
        "inv-1",
        "aisle-1",
        [
            UploadedFile(
                "1.jpg",
                BytesIO(b"fake-jpeg-bytes-a"),
                "image/jpeg",
                client_file_id=client_image_id,
                upload_batch_id="batch-ordered-1",
                ordered_capture_session_id=session.id,
                sequence_number=1,
            )
        ],
        principal=principal,
    )
    assert len(first.assets) == 1

    second = upload.execute(
        "inv-1",
        "aisle-1",
        [
            UploadedFile(
                "1.jpg",
                BytesIO(b"fake-jpeg-bytes-b-different"),
                "image/jpeg",
                client_file_id=client_image_id,
                upload_batch_id="batch-ordered-1",
                ordered_capture_session_id=session.id,
                sequence_number=1,
            )
        ],
        principal=principal,
    )
    assert second.assets == []
    assert len(second.errors) == 1
    assert second.errors[0].code == "IDEMPOTENCY_KEY_REUSED"
    assert len(list(asset_repo.list_by_aisle("aisle-1"))) == 1


def test_processing_rejected_when_session_uploading() -> None:
    create, _upload, session_repo, asset_repo, inv_repo, aisle_repo, clock, access = (
        _fixture()
    )
    principal = platform_principal()
    session = create.execute(
        CreateOrderedCaptureSessionCommand(
            inventory_id="inv-1", aisle_id="aisle-1", principal=principal
        )
    )
    now = clock.now()
    session.status = OrderedCaptureSessionStatus.UPLOADING
    session.updated_at = now
    session_repo.save(session)
    asset_repo.save(
        SourceAsset(
            id=str(uuid4()),
            aisle_id="aisle-1",
            type=SourceAssetType.PHOTO,
            original_filename="1.jpg",
            storage_path="/t/1.jpg",
            mime_type="image/jpeg",
            uploaded_at=now,
            upload_client_file_id=str(uuid4()),
            ordered_capture_session_id=session.id,
            sequence_number=1,
            sequence_source="CLIENT_ASSIGNED",
        )
    )
    job_repo = MemoryJobRepository()
    reconciler = InventoryStatusReconciler(inv_repo, aisle_repo, clock)
    use_case = StartAisleProcessingUseCase(
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        asset_repo=asset_repo,
        job_repo=job_repo,
        launch_service=AisleJobLaunchService(
            aisle_repo=aisle_repo,
            job_repo=job_repo,
            worker_launch_service=_StubWorkerLaunch(),
            clock=clock,
            status_reconciler=reconciler,
        ),
        stale_reconciler=JobStaleReconciler(
            job_repo=job_repo, clock=clock, stale_after_seconds=900, aisle_repo=aisle_repo
        ),
        access_policy=access,
        ordered_session_repo=session_repo,
    )
    with pytest.raises(ProcessingRejectedUnsealedSessionError) as exc_info:
        use_case.execute(
            StartAisleProcessingCommand(
                inventory_id="inv-1",
                aisle_id="aisle-1",
                principal=principal,
                ordered_capture_session_id=session.id,
            )
        )
    assert "SEALED" in str(exc_info.value) or "UPLOADING" in str(exc_info.value)
    assert exc_info.value.code == "PROCESSING_REJECTED_UNSEALED_SESSION"
