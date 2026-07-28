"""Phase 2 — inventory client-scope on aisle asset upload / list / delete."""

from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from unittest.mock import MagicMock

import pytest

from src.application.dto.uploaded_file import UploadedFile
from src.application.errors import InventoryNotFoundError
from src.application.services.inventory_status_reconciler import InventoryStatusReconciler
from src.application.use_cases.aisles.delete_aisle_source_asset import DeleteAisleSourceAssetUseCase
from src.application.use_cases.aisles.list_aisle_assets import ListAisleAssetsUseCase
from src.application.use_cases.aisles.upload_aisle_assets import UploadAisleAssetsUseCase
from src.auth.schemas import AuthUser
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.assets.entities import SourceAsset, SourceAssetType
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.infrastructure.repositories.memory_aisle_repository import MemoryAisleRepository
from src.infrastructure.repositories.memory_inventory_repository import MemoryInventoryRepository
from src.infrastructure.repositories.memory_job_repository import MemoryJobRepository
from src.infrastructure.repositories.memory_source_asset_repository import (
    MemorySourceAssetRepository,
)


class _Clock:
    def now(self) -> datetime:
        return datetime(2024, 1, 1, tzinfo=timezone.utc)


class _Storage:
    def __init__(self) -> None:
        self.saved: list[str] = []
        self.deleted: list[str] = []

    def save_file(self, key: str, data, content_type: str | None = None) -> str:  # noqa: ANN001
        self.saved.append(key)
        return key

    def delete_file(self, key: str) -> None:
        self.deleted.append(key)


def _inventory(client_id: str, inv_id: str = "inv-a") -> Inventory:
    now = datetime(2024, 1, 1, tzinfo=timezone.utc)
    return Inventory(
        id=inv_id,
        name="Inv",
        status=InventoryStatus.DRAFT,
        created_at=now,
        updated_at=now,
        client_id=client_id,
    )


def _aisle(inv_id: str = "inv-a", aisle_id: str = "aisle-1") -> Aisle:
    now = datetime(2024, 1, 1, tzinfo=timezone.utc)
    return Aisle(
        id=aisle_id,
        inventory_id=inv_id,
        code="A1",
        status=AisleStatus.CREATED,
        created_at=now,
        updated_at=now,
        is_active=True,
    )


def _user(client_id: str | None, *, role: str = "company_admin") -> AuthUser:
    return AuthUser(id="u1", username="op", role=role, client_id=client_id)


@pytest.fixture
def repos():
    inv = MemoryInventoryRepository()
    aisle = MemoryAisleRepository()
    asset = MemorySourceAssetRepository()
    inv.save(_inventory("client-a"))
    aisle.save(_aisle())
    return inv, aisle, asset


def test_upload_rejects_cross_client_before_storage(repos) -> None:
    inv_repo, aisle_repo, asset_repo = repos
    storage = _Storage()
    clock = _Clock()
    uc = UploadAisleAssetsUseCase(
        aisle_repo=aisle_repo,
        asset_repo=asset_repo,
        artifact_storage=storage,
        clock=clock,
        status_reconciler=InventoryStatusReconciler(
            inventory_repo=inv_repo, aisle_repo=aisle_repo, clock=clock
        ),
        inventory_repo=inv_repo,
    )
    uf = UploadedFile(
        original_filename="x.jpg",
        content_type="image/jpeg",
        file_obj=BytesIO(b"fake-jpeg-bytes"),
    )
    with pytest.raises(InventoryNotFoundError):
        uc.execute(
            "inv-a",
            "aisle-1",
            [uf],
            access_user=_user("client-b"),
        )
    assert storage.saved == []
    assert list(asset_repo.list_by_aisle("aisle-1")) == []


def test_list_and_delete_reject_cross_client(repos) -> None:
    inv_repo, aisle_repo, asset_repo = repos
    now = datetime(2024, 1, 1, tzinfo=timezone.utc)
    asset_repo.save(
        SourceAsset(
            id="asset-1",
            aisle_id="aisle-1",
            type=SourceAssetType.PHOTO,
            original_filename="a.jpg",
            storage_path="k",
            mime_type="image/jpeg",
            uploaded_at=now,
            storage_key="k",
        )
    )
    list_uc = ListAisleAssetsUseCase(
        aisle_repo=aisle_repo, asset_repo=asset_repo, inventory_repo=inv_repo
    )
    with pytest.raises(InventoryNotFoundError):
        list_uc.execute("inv-a", "aisle-1", access_user=_user("client-b"))

    del_uc = DeleteAisleSourceAssetUseCase(
        aisle_repo=aisle_repo,
        asset_repo=asset_repo,
        job_repo=MemoryJobRepository(),
        artifact_storage=_Storage(),
        clock=_Clock(),
        status_reconciler=MagicMock(),
        inventory_repo=inv_repo,
    )
    with pytest.raises(InventoryNotFoundError):
        del_uc.execute("inv-a", "aisle-1", "asset-1", access_user=_user("client-b"))


def test_platform_admin_can_cross_client(repos) -> None:
    inv_repo, aisle_repo, asset_repo = repos
    list_uc = ListAisleAssetsUseCase(
        aisle_repo=aisle_repo, asset_repo=asset_repo, inventory_repo=inv_repo
    )
    assert (
        list(
            list_uc.execute(
                "inv-a",
                "aisle-1",
                access_user=_user(None, role="platform_admin"),
            )
        )
        == []
    )


def test_same_client_list_ok(repos) -> None:
    inv_repo, aisle_repo, asset_repo = repos
    list_uc = ListAisleAssetsUseCase(
        aisle_repo=aisle_repo, asset_repo=asset_repo, inventory_repo=inv_repo
    )
    assert list(list_uc.execute("inv-a", "aisle-1", access_user=_user("client-a"))) == []
