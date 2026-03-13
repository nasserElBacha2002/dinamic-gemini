"""Tests for UploadAisleAssetsUseCase and ListAisleAssetsUseCase — v3.0 Épica 4."""

from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from typing import Dict, Optional, Sequence

import pytest

from src.application.errors import AisleNotFoundError, EmptyUploadError, UnsupportedAssetTypeError
from src.application.ports.repositories import AisleRepository, SourceAssetRepository
from src.application.ports.services import ArtifactStorage
from src.application.ports.clock import Clock
from src.application.use_cases.upload_aisle_assets import UploadAisleAssetsUseCase, UploadedFile
from src.application.use_cases.list_aisle_assets import ListAisleAssetsUseCase
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.assets.entities import SourceAsset, SourceAssetType
from src.domain.inventory.entities import Inventory, InventoryStatus


class FixedClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


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


class StubAssetRepo(SourceAssetRepository):
    def __init__(self) -> None:
        self._store: Dict[str, SourceAsset] = {}

    def save(self, asset: SourceAsset) -> None:
        self._store[asset.id] = asset

    def get_by_id(self, asset_id: str) -> Optional[SourceAsset]:
        return self._store.get(asset_id)

    def list_by_aisle(self, aisle_id: str) -> Sequence[SourceAsset]:
        return [a for a in self._store.values() if a.aisle_id == aisle_id]


class StubArtifactStorage(ArtifactStorage):
    def __init__(self) -> None:
        self._written: list[tuple[str, bytes, str]] = []

    def save_file(self, path: str, file_obj: BytesIO, content_type: str) -> str:
        content = file_obj.read()
        self._written.append((path, content, content_type))
        return path


def test_upload_aisle_assets_creates_assets_and_marks_aisle_assets_uploaded() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    aisle = Aisle("a1", "inv1", "A01", AisleStatus.CREATED, now, now)
    aisle_repo = StubAisleRepo()
    aisle_repo.save(aisle)
    asset_repo = StubAssetRepo()
    storage = StubArtifactStorage()
    clock = FixedClock(now)

    use_case = UploadAisleAssetsUseCase(
        aisle_repo=aisle_repo,
        asset_repo=asset_repo,
        artifact_storage=storage,
        clock=clock,
    )
    files = [
        UploadedFile("photo.jpg", BytesIO(b"fake_jpeg"), "image/jpeg"),
        UploadedFile("clip.mp4", BytesIO(b"fake_mp4"), "video/mp4"),
    ]
    created = use_case.execute("inv1", "a1", files)

    assert len(created) == 2
    assert all(a.aisle_id == "a1" for a in created)
    types = {a.type for a in created}
    assert types == {SourceAssetType.PHOTO, SourceAssetType.VIDEO}
    assert len(storage._written) == 2
    updated_aisle = aisle_repo.get_by_id("a1")
    assert updated_aisle is not None
    assert updated_aisle.status == AisleStatus.ASSETS_UPLOADED
    listed = asset_repo.list_by_aisle("a1")
    assert len(listed) == 2


def test_upload_aisle_assets_raises_when_aisle_not_found() -> None:
    aisle_repo = StubAisleRepo()
    asset_repo = StubAssetRepo()
    storage = StubArtifactStorage()
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)

    use_case = UploadAisleAssetsUseCase(
        aisle_repo=aisle_repo,
        asset_repo=asset_repo,
        artifact_storage=storage,
        clock=FixedClock(now),
    )
    files = [UploadedFile("x.jpg", BytesIO(b"x"), "image/jpeg")]

    with pytest.raises(AisleNotFoundError):
        use_case.execute("inv1", "nonexistent", files)


def test_upload_aisle_assets_raises_when_aisle_belongs_to_other_inventory() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    aisle = Aisle("a1", "inv1", "A01", AisleStatus.CREATED, now, now)
    aisle_repo = StubAisleRepo()
    aisle_repo.save(aisle)
    asset_repo = StubAssetRepo()
    storage = StubArtifactStorage()

    use_case = UploadAisleAssetsUseCase(
        aisle_repo=aisle_repo,
        asset_repo=asset_repo,
        artifact_storage=storage,
        clock=FixedClock(now),
    )
    files = [UploadedFile("x.jpg", BytesIO(b"x"), "image/jpeg")]

    with pytest.raises(AisleNotFoundError):
        use_case.execute("other_inv", "a1", files)


def test_upload_aisle_assets_raises_when_unsupported_content_type() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    aisle = Aisle("a1", "inv1", "A01", AisleStatus.CREATED, now, now)
    aisle_repo = StubAisleRepo()
    aisle_repo.save(aisle)
    asset_repo = StubAssetRepo()
    storage = StubArtifactStorage()

    use_case = UploadAisleAssetsUseCase(
        aisle_repo=aisle_repo,
        asset_repo=asset_repo,
        artifact_storage=storage,
        clock=FixedClock(now),
    )
    files = [UploadedFile("doc.pdf", BytesIO(b"pdf"), "application/pdf")]

    with pytest.raises(UnsupportedAssetTypeError):
        use_case.execute("inv1", "a1", files)


def test_upload_aisle_assets_raises_when_empty_files() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    aisle = Aisle("a1", "inv1", "A01", AisleStatus.CREATED, now, now)
    aisle_repo = StubAisleRepo()
    aisle_repo.save(aisle)
    asset_repo = StubAssetRepo()
    storage = StubArtifactStorage()

    use_case = UploadAisleAssetsUseCase(
        aisle_repo=aisle_repo,
        asset_repo=asset_repo,
        artifact_storage=storage,
        clock=FixedClock(now),
    )

    with pytest.raises(EmptyUploadError, match="At least one file"):
        use_case.execute("inv1", "a1", [])


def test_list_aisle_assets_returns_assets_for_aisle() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    aisle = Aisle("a1", "inv1", "A01", AisleStatus.ASSETS_UPLOADED, now, now)
    aisle_repo = StubAisleRepo()
    aisle_repo.save(aisle)
    asset_repo = StubAssetRepo()
    asset_repo.save(
        SourceAsset(
            "x1", "a1", SourceAssetType.PHOTO, "f.jpg", "/path/f.jpg", "image/jpeg", now
        )
    )

    use_case = ListAisleAssetsUseCase(aisle_repo=aisle_repo, asset_repo=asset_repo)
    result = use_case.execute("inv1", "a1")

    assert len(result) == 1
    assert result[0].id == "x1"
    assert result[0].original_filename == "f.jpg"


def test_list_aisle_assets_raises_when_aisle_not_found() -> None:
    aisle_repo = StubAisleRepo()
    asset_repo = StubAssetRepo()
    use_case = ListAisleAssetsUseCase(aisle_repo=aisle_repo, asset_repo=asset_repo)

    with pytest.raises(AisleNotFoundError):
        use_case.execute("inv1", "nonexistent")
