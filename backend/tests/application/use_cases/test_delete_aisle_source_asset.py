"""Tests for DeleteAisleSourceAssetUseCase."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import cast

import pytest

from src.application.errors import (
    AisleNotFoundError,
    AisleSourceAssetMutationBlockedError,
    SourceAssetNotFoundForAisleError,
)
from src.application.ports.clock import Clock
from src.application.ports.contracts import AisleAssetRollup
from src.application.ports.repositories import (
    AisleRepository,
    InventoryRepository,
    JobRepository,
    SourceAssetRepository,
)
from src.application.ports.services import ArtifactStorage
from src.application.services.inventory_status_reconciler import InventoryStatusReconciler
from src.application.use_cases.aisles.delete_aisle_source_asset import DeleteAisleSourceAssetUseCase
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.assets.entities import SourceAsset, SourceAssetType
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.domain.jobs.entities import Job, JobStatus
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

    def list_by_aisle(self, aisle_id: str) -> Sequence[SourceAsset]:
        return [a for a in self._store.values() if a.aisle_id == aisle_id]

    def get_by_capture_session_item_id(self, capture_session_item_id: str) -> SourceAsset | None:
        return None

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
        self._deleted: list[str] = []

    def save_file(self, path: str, file_obj, content_type: str) -> str:
        return path

    def put_object(self, path: str, file_obj, content_type: str) -> StoredArtifact:
        return StoredArtifact(
            storage_provider="local",
            storage_bucket="",
            storage_key=path,
            content_type=content_type,
            file_size_bytes=0,
            etag="",
        )

    def delete_file(self, path: str) -> None:
        self._deleted.append(path)


class InMemoryJobRepo(JobRepository):
    def __init__(self, jobs: Sequence[Job] | None = None) -> None:
        self._store: dict[str, Job] = {j.id: j for j in (jobs or [])}

    def save(self, job: Job) -> None:
        self._store[job.id] = job

    def get_by_id(self, job_id: str) -> Job | None:
        return self._store.get(job_id)

    def get_latest_by_target(self, target_type: str, target_id: str) -> Job | None:
        return None

    def get_latest_by_targets(self, target_type: str, target_ids: Sequence[str]) -> dict[str, Job]:
        return {}

    def list_jobs_for_target(
        self, target_type: str, target_id: str, *, limit: int = 50
    ) -> Sequence[Job]:
        return [
            j
            for j in self._store.values()
            if j.target_type == target_type and j.target_id == target_id
        ]


def _asset(
    asset_id: str,
    aisle_id: str,
    *,
    uploaded: datetime | None = None,
    storage_key: str = "uploads/aisles/a1/raw/x.jpg",
) -> SourceAsset:
    now = uploaded or datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    return SourceAsset(
        id=asset_id,
        aisle_id=aisle_id,
        type=SourceAssetType.PHOTO,
        original_filename="x.jpg",
        storage_path=storage_key,
        mime_type="image/jpeg",
        uploaded_at=now,
        storage_key=storage_key,
    )


def test_delete_removes_asset_storage_and_reverts_aisle_when_last() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    inv = Inventory("inv1", "Wh", InventoryStatus.DRAFT, now, now)
    inv_repo = StubInventoryRepo([inv])
    aisle = Aisle("a1", "inv1", "A01", AisleStatus.ASSETS_UPLOADED, now, now)
    aisle_repo = StubAisleRepo()
    aisle_repo.save(aisle)
    asset_repo = StubAssetRepo()
    asset_repo.save(_asset("ast1", "a1", uploaded=now))
    storage = StubArtifactStorage()
    clock = cast(Clock, FixedClock(now))
    reconciler = InventoryStatusReconciler(inv_repo, aisle_repo, clock)
    use_case = DeleteAisleSourceAssetUseCase(
        aisle_repo=aisle_repo,
        asset_repo=asset_repo,
        job_repo=InMemoryJobRepo([]),
        artifact_storage=storage,
        clock=clock,
        status_reconciler=reconciler,
    )

    use_case.execute("inv1", "a1", "ast1")

    assert asset_repo.get_by_id("ast1") is None
    assert storage._deleted == ["uploads/aisles/a1/raw/x.jpg"]
    updated = aisle_repo.get_by_id("a1")
    assert updated is not None
    assert updated.status == AisleStatus.CREATED


def test_delete_blocked_when_active_job() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    inv = Inventory("inv1", "Wh", InventoryStatus.DRAFT, now, now)
    inv_repo = StubInventoryRepo([inv])
    aisle = Aisle("a1", "inv1", "A01", AisleStatus.ASSETS_UPLOADED, now, now)
    aisle_repo = StubAisleRepo()
    aisle_repo.save(aisle)
    asset_repo = StubAssetRepo()
    asset_repo.save(_asset("ast1", "a1", uploaded=now))
    job = Job(
        id="j1",
        target_type="aisle",
        target_id="a1",
        job_type="process_aisle",
        status=JobStatus.RUNNING,
        payload_json={},
        created_at=now,
        updated_at=now,
    )
    job_repo = InMemoryJobRepo([job])
    storage = StubArtifactStorage()
    clock = cast(Clock, FixedClock(now))
    reconciler = InventoryStatusReconciler(inv_repo, aisle_repo, clock)
    use_case = DeleteAisleSourceAssetUseCase(
        aisle_repo=aisle_repo,
        asset_repo=asset_repo,
        job_repo=job_repo,
        artifact_storage=storage,
        clock=clock,
        status_reconciler=reconciler,
    )

    with pytest.raises(AisleSourceAssetMutationBlockedError):
        use_case.execute("inv1", "a1", "ast1")

    assert asset_repo.get_by_id("ast1") is not None
    assert storage._deleted == []


def test_delete_raises_when_asset_wrong_aisle() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    inv = Inventory("inv1", "Wh", InventoryStatus.DRAFT, now, now)
    inv_repo = StubInventoryRepo([inv])
    aisle = Aisle("a1", "inv1", "A01", AisleStatus.ASSETS_UPLOADED, now, now)
    aisle_repo = StubAisleRepo()
    aisle_repo.save(aisle)
    asset_repo = StubAssetRepo()
    asset_repo.save(_asset("ast1", "other-aisle", uploaded=now))
    clock = cast(Clock, FixedClock(now))
    reconciler = InventoryStatusReconciler(inv_repo, aisle_repo, clock)
    use_case = DeleteAisleSourceAssetUseCase(
        aisle_repo=aisle_repo,
        asset_repo=asset_repo,
        job_repo=InMemoryJobRepo([]),
        artifact_storage=StubArtifactStorage(),
        clock=clock,
        status_reconciler=reconciler,
    )

    with pytest.raises(SourceAssetNotFoundForAisleError):
        use_case.execute("inv1", "a1", "ast1")


def test_delete_raises_aisle_not_found() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    inv = Inventory("inv1", "Wh", InventoryStatus.DRAFT, now, now)
    inv_repo = StubInventoryRepo([inv])
    aisle_repo = StubAisleRepo()
    clock = cast(Clock, FixedClock(now))
    reconciler = InventoryStatusReconciler(inv_repo, aisle_repo, clock)
    use_case = DeleteAisleSourceAssetUseCase(
        aisle_repo=aisle_repo,
        asset_repo=StubAssetRepo(),
        job_repo=InMemoryJobRepo([]),
        artifact_storage=StubArtifactStorage(),
        clock=clock,
        status_reconciler=reconciler,
    )

    with pytest.raises(AisleNotFoundError):
        use_case.execute("inv1", "missing", "ast1")
