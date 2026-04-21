"""Unit tests for AisleSourceAssetMaterializer."""

from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from typing import Dict, Optional, Sequence

from src.application.dto.uploaded_file import UploadedFile
from src.application.ports.contracts import AisleAssetRollup
from src.application.ports.repositories import AisleRepository, InventoryRepository, SourceAssetRepository
from src.application.services.aisle_source_asset_materializer import AisleSourceAssetMaterializer
from src.application.services.inventory_status_reconciler import InventoryStatusReconciler
from src.application.ports.services import ArtifactStorage
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.assets.entities import SourceAsset, SourceAssetType
from src.domain.inventory.entities import Inventory, InventoryStatus


class FixedClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


class StubInventoryRepo(InventoryRepository):
    def __init__(self, inv: Inventory) -> None:
        self._inv = inv

    def save(self, inventory: Inventory) -> None:
        self._inv = inventory

    def get_by_id(self, inventory_id: str) -> Optional[Inventory]:
        return self._inv if self._inv.id == inventory_id else None

    def list_all(self) -> Sequence[Inventory]:
        return [self._inv]


class StubAisleRepo(AisleRepository):
    def __init__(self, aisle: Aisle) -> None:
        self._aisle = aisle
        self.saved: list[Aisle] = []

    def save(self, aisle: Aisle) -> None:
        self.saved.append(aisle)

    def get_by_id(self, aisle_id: str) -> Optional[Aisle]:
        return self._aisle if self._aisle.id == aisle_id else None

    def list_by_inventory(self, inventory_id: str) -> Sequence[Aisle]:
        return [self._aisle] if self._aisle.inventory_id == inventory_id else []

    def get_by_inventory_and_code(self, inventory_id: str, code: str) -> Optional[Aisle]:
        return None


class StubAssetRepo(SourceAssetRepository):
    def __init__(self) -> None:
        self._store: Dict[str, SourceAsset] = {}

    def save(self, asset: SourceAsset) -> None:
        self._store[asset.id] = asset

    def get_by_id(self, asset_id: str) -> Optional[SourceAsset]:
        return self._store.get(asset_id)

    def delete_by_id(self, asset_id: str) -> bool:
        return self._store.pop(asset_id, None) is not None

    def list_by_aisle(self, aisle_id: str) -> Sequence[SourceAsset]:
        return [a for a in self._store.values() if a.aisle_id == aisle_id]

    def summarize_assets_for_aisles(self, aisle_ids: Sequence[str]) -> Dict[str, AisleAssetRollup]:
        return {}


class StubArtifactStorage(ArtifactStorage):
    def __init__(self) -> None:
        self._written: list[tuple[str, bytes, str]] = []
        self._deleted: list[str] = []

    def save_file(self, path: str, file_obj: BytesIO, content_type: str) -> str:
        content = file_obj.read()
        self._written.append((path, content, content_type))
        return path

    def delete_file(self, path: str) -> None:
        self._deleted.append(path)


def test_materializer_persist_then_finalize_marks_aisle_and_reconciles() -> None:
    now = datetime(2025, 6, 1, 10, 0, 0, tzinfo=timezone.utc)
    inv = Inventory("inv1", "Wh", InventoryStatus.DRAFT, now, now)
    aisle = Aisle("a1", "inv1", "A01", AisleStatus.CREATED, now, now)
    inv_repo = StubInventoryRepo(inv)
    aisle_repo = StubAisleRepo(aisle)
    asset_repo = StubAssetRepo()
    storage = StubArtifactStorage()
    clock = FixedClock(now)
    reconciler = InventoryStatusReconciler(inv_repo, aisle_repo, clock)

    m = AisleSourceAssetMaterializer(
        aisle_repo=aisle_repo,
        asset_repo=asset_repo,
        artifact_storage=storage,
        status_reconciler=reconciler,
    )
    uf = UploadedFile("p.jpg", BytesIO(b"x"), "image/jpeg")
    asset, key = m.persist_uploaded_file_as_source_asset(aisle_id="a1", uploaded=uf, now=now)
    assert asset.aisle_id == "a1"
    assert asset.type == SourceAssetType.PHOTO
    assert len(storage._written) == 1
    assert asset_repo.get_by_id(asset.id) is not None

    m.finalize_aisle_after_source_assets_changed(aisle=aisle, inventory_id="inv1", now=now)
    assert aisle.status == AisleStatus.ASSETS_UPLOADED
    assert len(aisle_repo.saved) >= 1
    assert key  # rollback key is non-empty string
