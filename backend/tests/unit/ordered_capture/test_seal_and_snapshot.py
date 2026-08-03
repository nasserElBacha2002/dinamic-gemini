"""Unit tests — seal + process gate for ordered capture sessions."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from src.application.dto.access_principal import AccessPrincipal
from src.application.errors import (
    OrderedCaptureSealRejectedError,
    ProcessingRejectedUnsealedSessionError,
)
from src.application.services.job_source_asset_snapshot import build_job_source_asset_links
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
from src.infrastructure.repositories.memory_ordered_capture_session_repository import (
    MemoryOrderedCaptureSessionRepository,
)
from src.infrastructure.repositories.memory_source_asset_repository import (
    MemorySourceAssetRepository,
)


class _FixedClock:
    def now(self) -> datetime:
        return datetime(2026, 7, 17, tzinfo=timezone.utc)


class _AllowAllPolicy:
    def require_aisle(self, inventory_id: str, aisle_id: str, principal: AccessPrincipal):
        return self._aisle

    def __init__(self, aisle: Aisle) -> None:
        self._aisle = aisle


def _principal() -> AccessPrincipal:
    return AccessPrincipal(
        actor_id="user-1",
        client_id="client-1",
        roles=frozenset({"admin"}),
        is_platform=True,
    )


def _setup():
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
    policy = _AllowAllPolicy(aisle)
    clock = _FixedClock()
    create = CreateOrderedCaptureSessionUseCase(
        session_repo=session_repo,
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        access_policy=policy,  # type: ignore[arg-type]
        clock=clock,
    )
    seal = SealOrderedCaptureSessionUseCase(
        session_repo=session_repo,
        asset_repo=asset_repo,
        access_policy=policy,  # type: ignore[arg-type]
        clock=clock,
    )
    return create, seal, session_repo, asset_repo, aisle


def test_seal_complete_and_idempotent() -> None:
    create, seal, session_repo, asset_repo, _aisle = _setup()
    session = create.execute(
        CreateOrderedCaptureSessionCommand(
            inventory_id="inv-1", aisle_id="aisle-1", principal=_principal()
        )
    )
    now = datetime(2026, 7, 17, tzinfo=timezone.utc)
    for n in range(1, 8):
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
    cmd = SealOrderedCaptureSessionCommand(
        session_id=session.id,
        expected_asset_count=7,
        sequence_version=1,
        principal=_principal(),
    )
    sealed = seal.execute(cmd)
    assert sealed.status == OrderedCaptureSessionStatus.SEALED
    again = seal.execute(cmd)
    assert again.id == sealed.id
    assert again.sealed_at == sealed.sealed_at


def test_seal_incomplete_rejected() -> None:
    create, seal, _session_repo, asset_repo, _aisle = _setup()
    session = create.execute(
        CreateOrderedCaptureSessionCommand(
            inventory_id="inv-1", aisle_id="aisle-1", principal=_principal()
        )
    )
    now = datetime(2026, 7, 17, tzinfo=timezone.utc)
    for n in range(1, 7):
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
    with pytest.raises(OrderedCaptureSealRejectedError):
        seal.execute(
            SealOrderedCaptureSessionCommand(
                session_id=session.id,
                expected_asset_count=7,
                sequence_version=1,
                principal=_principal(),
            )
        )


def test_job_snapshot_uses_sequence_as_position_order() -> None:
    now = datetime(2026, 7, 17, tzinfo=timezone.utc)
    assets = [
        SourceAsset(
            id=f"id-{n}",
            aisle_id="aisle-1",
            type=SourceAssetType.PHOTO,
            original_filename=f"{n}.jpg",
            storage_path=f"/t/{n}.jpg",
            mime_type="image/jpeg",
            uploaded_at=now,
            upload_client_file_id=f"c-{n}",
            ordered_capture_session_id="sess",
            sequence_number=n,
            sequence_source="CLIENT_ASSIGNED",
        )
        for n in (3, 1, 2)
    ]
    links = build_job_source_asset_links(job_id="job-1", assets=assets)
    assert [link.position_order for link in links] == [1, 2, 3]
    assert [link.sequence_number for link in links] == [1, 2, 3]


def test_processing_rejected_helper_message() -> None:
    err = ProcessingRejectedUnsealedSessionError("must be sealed")
    assert err.code == "PROCESSING_REJECTED_UNSEALED_SESSION"
