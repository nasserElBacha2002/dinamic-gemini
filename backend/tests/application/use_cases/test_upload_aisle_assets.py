"""Tests for UploadAisleAssetsUseCase and ListAisleAssetsUseCase — v3.0 Épica 4."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime, timezone
from io import BytesIO

import pytest

from src.application.errors import AisleNotFoundError, EmptyUploadError, UnsupportedAssetTypeError
from src.application.ports.contracts import AisleAssetRollup
from src.application.ports.repositories import (
    AisleRepository,
    InventoryRepository,
    SourceAssetRepository,
)
from src.application.ports.services import ArtifactStorage
from src.application.services.inventory_status_reconciler import InventoryStatusReconciler
from src.application.use_cases.aisles.list_aisle_assets import ListAisleAssetsUseCase
from src.application.use_cases.aisles.upload_aisle_assets import UploadAisleAssetsUseCase, UploadedFile
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.assets.entities import SourceAsset, SourceAssetType
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.infrastructure.storage.artifact_store import StoredArtifact


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

    def get_by_id(self, inventory_id: str) -> Inventory | None:
        return self._store.get(inventory_id)

    def list_all(self) -> Sequence[Inventory]:
        return list(self._store.values())


class StubAisleRepo(AisleRepository):
    def __init__(self) -> None:
        self._store: dict[str, Aisle] = {}

    def save(self, aisle: Aisle) -> None:
        self._store[aisle.id] = aisle

    def get_by_id(self, aisle_id: str) -> Aisle | None:
        return self._store.get(aisle_id)

    def list_by_inventory(self, inventory_id: str) -> Sequence[Aisle]:
        return [a for a in self._store.values() if a.inventory_id == inventory_id]

    def get_by_inventory_and_code(self, inventory_id: str, code: str) -> Aisle | None:
        for a in self._store.values():
            if a.inventory_id == inventory_id and a.code == code.strip():
                return a
        return None


class StubAssetRepo(SourceAssetRepository):
    def __init__(self) -> None:
        self._store: dict[str, SourceAsset] = {}

    def save(self, asset: SourceAsset) -> None:
        self._store[asset.id] = asset

    def get_by_id(self, asset_id: str) -> SourceAsset | None:
        return self._store.get(asset_id)

    def delete_by_id(self, asset_id: str) -> bool:
        if asset_id in self._store:
            del self._store[asset_id]
            return True
        return False

    def get_by_capture_session_item_id(self, capture_session_item_id: str) -> SourceAsset | None:
        return None

    def list_by_aisle(self, aisle_id: str) -> Sequence[SourceAsset]:
        return [a for a in self._store.values() if a.aisle_id == aisle_id]

    def summarize_assets_for_aisles(self, aisle_ids: Sequence[str]) -> dict[str, AisleAssetRollup]:
        wanted = set(aisle_ids)
        by_aisle: dict[str, list[SourceAsset]] = defaultdict(list)
        for a in self._store.values():
            if a.aisle_id in wanted:
                by_aisle[a.aisle_id].append(a)
        out: dict[str, AisleAssetRollup] = {}
        for aid, assets in by_aisle.items():
            if not assets:
                continue
            last = max(x.uploaded_at for x in assets)
            out[aid] = AisleAssetRollup(count=len(assets), last_uploaded_at=last)
        return out


class StubArtifactStorage(ArtifactStorage):
    def __init__(self) -> None:
        self._written: list[tuple[str, bytes, str]] = []
        self._deleted: list[str] = []

    def save_file(self, path: str, file_obj: BytesIO, content_type: str) -> str:
        content = file_obj.read()
        self._written.append((path, content, content_type))
        return path

    def put_object(self, path: str, file_obj: BytesIO, content_type: str) -> StoredArtifact:
        content = file_obj.read()
        self._written.append((path, content, content_type))
        return StoredArtifact(
            storage_provider="s3",
            storage_bucket="bucket-a",
            storage_key=path,
            content_type=content_type,
            file_size_bytes=len(content),
            etag="etag-test",
        )

    def delete_file(self, path: str) -> None:
        self._deleted.append(path)


class FailingAssetRepo(StubAssetRepo):
    def save(self, asset: SourceAsset) -> None:
        raise RuntimeError("simulated db failure")


class CanonicalLogicalKeyArtifactStorage(StubArtifactStorage):
    """Like production S3 adapter: persisted ``storage_key`` is logical (no bucket prefix)."""

    def put_object(self, path: str, file_obj: BytesIO, content_type: str) -> StoredArtifact:
        content = file_obj.read()
        self._written.append((path, content, content_type))
        return StoredArtifact(
            storage_provider="s3",
            storage_bucket="bucket-a",
            storage_key=path,
            content_type=content_type,
            file_size_bytes=len(content),
            etag="etag-test",
        )


def test_upload_aisle_assets_creates_assets_and_marks_aisle_assets_uploaded() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    inv = Inventory("inv1", "Wh", InventoryStatus.DRAFT, now, now)
    inv_repo = StubInventoryRepo([inv])
    aisle = Aisle("a1", "inv1", "A01", AisleStatus.CREATED, now, now)
    aisle_repo = StubAisleRepo()
    aisle_repo.save(aisle)
    asset_repo = StubAssetRepo()
    storage = StubArtifactStorage()
    clock = FixedClock(now)
    reconciler = InventoryStatusReconciler(inv_repo, aisle_repo, clock)

    use_case = UploadAisleAssetsUseCase(
        aisle_repo=aisle_repo,
        asset_repo=asset_repo,
        artifact_storage=storage,
        clock=clock,
        status_reconciler=reconciler,
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
    assert all(a.storage_provider == "s3" for a in created)
    assert all(a.storage_bucket == "bucket-a" for a in created)
    assert all((a.storage_key or "").startswith("uploads/aisles/a1/raw/") for a in created)
    assert all(a.storage_path.startswith("uploads/aisles/a1/raw/") for a in created)
    assert all(a.file_size_bytes is not None for a in created)
    updated_aisle = aisle_repo.get_by_id("a1")
    assert updated_aisle is not None
    assert updated_aisle.status == AisleStatus.ASSETS_UPLOADED
    listed = asset_repo.list_by_aisle("a1")
    assert len(listed) == 2
    assert inv_repo.get_by_id("inv1") is not None
    assert inv_repo.get_by_id("inv1").status != InventoryStatus.DRAFT


def test_upload_aisle_assets_raises_when_aisle_not_found() -> None:
    aisle_repo = StubAisleRepo()
    inv_repo = StubInventoryRepo([])
    asset_repo = StubAssetRepo()
    storage = StubArtifactStorage()
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    reconciler = InventoryStatusReconciler(inv_repo, aisle_repo, FixedClock(now))

    use_case = UploadAisleAssetsUseCase(
        aisle_repo=aisle_repo,
        asset_repo=asset_repo,
        artifact_storage=storage,
        clock=FixedClock(now),
        status_reconciler=reconciler,
    )
    files = [UploadedFile("x.jpg", BytesIO(b"x"), "image/jpeg")]

    with pytest.raises(AisleNotFoundError):
        use_case.execute("inv1", "nonexistent", files)


def test_upload_aisle_assets_leaves_storage_orphan_when_db_save_fails() -> None:
    """Storage is written before DB save; on save failure the use case does not compensate deletes."""
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    inv = Inventory("inv1", "Wh", InventoryStatus.DRAFT, now, now)
    inv_repo = StubInventoryRepo([inv])
    aisle = Aisle("a1", "inv1", "A01", AisleStatus.CREATED, now, now)
    aisle_repo = StubAisleRepo()
    aisle_repo.save(aisle)
    asset_repo = FailingAssetRepo()
    storage = StubArtifactStorage()
    reconciler = InventoryStatusReconciler(inv_repo, aisle_repo, FixedClock(now))

    use_case = UploadAisleAssetsUseCase(
        aisle_repo=aisle_repo,
        asset_repo=asset_repo,
        artifact_storage=storage,
        clock=FixedClock(now),
        status_reconciler=reconciler,
    )
    files = [UploadedFile("photo.jpg", BytesIO(b"fake_jpeg"), "image/jpeg")]

    with pytest.raises(RuntimeError, match="simulated db failure"):
        use_case.execute("inv1", "a1", files)
    assert storage._deleted == []
    assert len(storage._written) == 1


def test_upload_aisle_assets_failed_save_leaves_canonical_storage_key_without_delete() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    inv = Inventory("inv1", "Wh", InventoryStatus.DRAFT, now, now)
    inv_repo = StubInventoryRepo([inv])
    aisle = Aisle("a1", "inv1", "A01", AisleStatus.CREATED, now, now)
    aisle_repo = StubAisleRepo()
    aisle_repo.save(aisle)
    asset_repo = FailingAssetRepo()
    storage = CanonicalLogicalKeyArtifactStorage()
    reconciler = InventoryStatusReconciler(inv_repo, aisle_repo, FixedClock(now))

    use_case = UploadAisleAssetsUseCase(
        aisle_repo=aisle_repo,
        asset_repo=asset_repo,
        artifact_storage=storage,
        clock=FixedClock(now),
        status_reconciler=reconciler,
    )
    files = [UploadedFile("photo.jpg", BytesIO(b"fake_jpeg"), "image/jpeg")]

    with pytest.raises(RuntimeError, match="simulated db failure"):
        use_case.execute("inv1", "a1", files)
    assert storage._deleted == []
    assert len(storage._written) == 1


def test_upload_aisle_assets_raises_when_aisle_belongs_to_other_inventory() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    aisle = Aisle("a1", "inv1", "A01", AisleStatus.CREATED, now, now)
    aisle_repo = StubAisleRepo()
    aisle_repo.save(aisle)
    inv_repo = StubInventoryRepo([])
    asset_repo = StubAssetRepo()
    storage = StubArtifactStorage()
    reconciler = InventoryStatusReconciler(inv_repo, aisle_repo, FixedClock(now))

    use_case = UploadAisleAssetsUseCase(
        aisle_repo=aisle_repo,
        asset_repo=asset_repo,
        artifact_storage=storage,
        clock=FixedClock(now),
        status_reconciler=reconciler,
    )
    files = [UploadedFile("x.jpg", BytesIO(b"x"), "image/jpeg")]

    with pytest.raises(AisleNotFoundError):
        use_case.execute("other_inv", "a1", files)


def test_upload_aisle_assets_raises_when_unsupported_content_type() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    aisle = Aisle("a1", "inv1", "A01", AisleStatus.CREATED, now, now)
    aisle_repo = StubAisleRepo()
    aisle_repo.save(aisle)
    inv_repo = StubInventoryRepo([Inventory("inv1", "W", InventoryStatus.DRAFT, now, now)])
    asset_repo = StubAssetRepo()
    storage = StubArtifactStorage()
    reconciler = InventoryStatusReconciler(inv_repo, aisle_repo, FixedClock(now))

    use_case = UploadAisleAssetsUseCase(
        aisle_repo=aisle_repo,
        asset_repo=asset_repo,
        artifact_storage=storage,
        clock=FixedClock(now),
        status_reconciler=reconciler,
    )
    files = [UploadedFile("doc.pdf", BytesIO(b"pdf"), "application/pdf")]

    with pytest.raises(UnsupportedAssetTypeError):
        use_case.execute("inv1", "a1", files)


def test_upload_aisle_assets_raises_when_empty_files() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    aisle = Aisle("a1", "inv1", "A01", AisleStatus.CREATED, now, now)
    aisle_repo = StubAisleRepo()
    aisle_repo.save(aisle)
    inv_repo = StubInventoryRepo([Inventory("inv1", "W", InventoryStatus.DRAFT, now, now)])
    asset_repo = StubAssetRepo()
    storage = StubArtifactStorage()
    reconciler = InventoryStatusReconciler(inv_repo, aisle_repo, FixedClock(now))

    use_case = UploadAisleAssetsUseCase(
        aisle_repo=aisle_repo,
        asset_repo=asset_repo,
        artifact_storage=storage,
        clock=FixedClock(now),
        status_reconciler=reconciler,
    )

    with pytest.raises(EmptyUploadError, match="At least one file"):
        use_case.execute("inv1", "a1", [])


def test_upload_aisle_assets_rejects_video_extension_labeled_as_image() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    aisle = Aisle("a1", "inv1", "A01", AisleStatus.CREATED, now, now)
    aisle_repo = StubAisleRepo()
    aisle_repo.save(aisle)
    inv_repo = StubInventoryRepo([Inventory("inv1", "W", InventoryStatus.DRAFT, now, now)])
    asset_repo = StubAssetRepo()
    storage = StubArtifactStorage()
    reconciler = InventoryStatusReconciler(inv_repo, aisle_repo, FixedClock(now))

    use_case = UploadAisleAssetsUseCase(
        aisle_repo=aisle_repo,
        asset_repo=asset_repo,
        artifact_storage=storage,
        clock=FixedClock(now),
        status_reconciler=reconciler,
    )
    files = [UploadedFile("camera_capture.mp4", BytesIO(b"bad"), "image/jpeg")]

    with pytest.raises(UnsupportedAssetTypeError, match="Invalid photo upload"):
        use_case.execute("inv1", "a1", files)


def test_list_aisle_assets_returns_assets_for_aisle() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    aisle = Aisle("a1", "inv1", "A01", AisleStatus.ASSETS_UPLOADED, now, now)
    aisle_repo = StubAisleRepo()
    aisle_repo.save(aisle)
    asset_repo = StubAssetRepo()
    asset_repo.save(
        SourceAsset("x1", "a1", SourceAssetType.PHOTO, "f.jpg", "/path/f.jpg", "image/jpeg", now)
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


def test_list_aisle_assets_get_validated_aisle_matches_execute_rules() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    aisle = Aisle("a1", "inv1", "A01", AisleStatus.ASSETS_UPLOADED, now, now)
    aisle_repo = StubAisleRepo()
    aisle_repo.save(aisle)
    asset_repo = StubAssetRepo()
    uc = ListAisleAssetsUseCase(aisle_repo=aisle_repo, asset_repo=asset_repo)
    got = uc.get_validated_aisle("inv1", "a1")
    assert got.id == "a1"
    assert got.inventory_id == "inv1"

    with pytest.raises(AisleNotFoundError):
        uc.get_validated_aisle("wrong-inv", "a1")
