from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from typing import Dict, Optional, Sequence

import pytest

from src.application.errors import InventoryVisualReferenceNotFoundError
from src.application.ports.repositories import InventoryRepository, InventoryVisualReferenceRepository
from src.application.ports.services import ArtifactStorage
from src.application.use_cases.manage_inventory_visual_references import (
    DeleteInventoryVisualReferenceUseCase,
    ReplaceInventoryVisualReferenceUseCase,
)
from src.application.use_cases.upload_inventory_visual_references import UploadedVisualReferenceFile
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.domain.inventory.visual_reference import InventoryVisualReference
from src.infrastructure.storage.artifact_store import StoredArtifact


class StubInventoryRepo(InventoryRepository):
    def __init__(self) -> None:
        self._store: Dict[str, Inventory] = {}

    def save(self, inventory: Inventory) -> None:
        self._store[inventory.id] = inventory

    def get_by_id(self, inventory_id: str) -> Optional[Inventory]:
        return self._store.get(inventory_id)

    def list_all(self) -> Sequence[Inventory]:
        return list(self._store.values())


class StubVisualReferenceRepo(InventoryVisualReferenceRepository):
    def __init__(self) -> None:
        self._store: Dict[str, InventoryVisualReference] = {}

    def get_by_id(self, reference_id: str) -> Optional[InventoryVisualReference]:
        return self._store.get(reference_id)

    def create(self, reference: InventoryVisualReference) -> None:
        self._store[reference.id] = reference

    def create_many(self, references: Sequence[InventoryVisualReference]) -> None:
        for reference in references:
            self._store[reference.id] = reference

    def list_by_inventory(self, inventory_id: str) -> Sequence[InventoryVisualReference]:
        refs = [r for r in self._store.values() if r.inventory_id == inventory_id]
        refs.sort(key=lambda r: (r.created_at, r.id))
        return refs

    def update(self, reference: InventoryVisualReference) -> None:
        if reference.id not in self._store:
            raise KeyError(reference.id)
        self._store[reference.id] = reference

    def delete(self, reference_id: str) -> None:
        self._store.pop(reference_id, None)


class StubArtifactStorage(ArtifactStorage):
    def __init__(self) -> None:
        self.deleted: list[str] = []
        self.written: list[str] = []

    def save_file(self, path: str, file_obj: BytesIO, content_type: str) -> str:
        self.written.append(path)
        return path

    def put_object(self, path: str, file_obj: BytesIO, content_type: str) -> StoredArtifact:
        self.written.append(path)
        content = file_obj.read()
        return StoredArtifact(
            storage_provider="s3",
            storage_bucket="bucket-r",
            storage_key=path,
            content_type=content_type,
            file_size_bytes=len(content),
            etag="etag-r",
        )

    def delete_file(self, path: str) -> None:
        self.deleted.append(path)


def _inventory(now: datetime) -> Inventory:
    return Inventory(
        id="inv-1",
        name="Inventory",
        status=InventoryStatus.DRAFT,
        created_at=now,
        updated_at=now,
    )


def _reference(now: datetime) -> InventoryVisualReference:
    return InventoryVisualReference(
        id="ref-1",
        inventory_id="inv-1",
        filename="front.jpg",
        storage_path="inventories/inv-1/visual_references/ref-1.jpg",
        mime_type="image/jpeg",
        file_size=10,
        created_at=now,
        storage_provider="s3",
        storage_bucket="bucket-r",
        storage_key="inventories/inv-1/visual_references/ref-1.jpg",
        content_type="image/jpeg",
        file_size_bytes=10,
        etag="etag-old",
    )


def test_delete_inventory_visual_reference_removes_record_and_artifact() -> None:
    now = datetime(2025, 4, 1, 12, 0, 0, tzinfo=timezone.utc)
    inv_repo = StubInventoryRepo()
    inv_repo.save(_inventory(now))
    ref_repo = StubVisualReferenceRepo()
    ref_repo.create(_reference(now))
    storage = StubArtifactStorage()

    use_case = DeleteInventoryVisualReferenceUseCase(inv_repo, ref_repo, storage)
    use_case.execute("inv-1", "ref-1")

    assert ref_repo.get_by_id("ref-1") is None
    assert storage.deleted == ["inventories/inv-1/visual_references/ref-1.jpg"]


def test_replace_inventory_visual_reference_updates_record_and_cleans_old_artifact() -> None:
    now = datetime(2025, 4, 1, 12, 0, 0, tzinfo=timezone.utc)
    inv_repo = StubInventoryRepo()
    inv_repo.save(_inventory(now))
    ref_repo = StubVisualReferenceRepo()
    ref_repo.create(_reference(now))
    storage = StubArtifactStorage()

    use_case = ReplaceInventoryVisualReferenceUseCase(inv_repo, ref_repo, storage)
    updated = use_case.execute(
        "inv-1",
        "ref-1",
        UploadedVisualReferenceFile(
            original_filename="updated.png",
            file_obj=BytesIO(b"new-image"),
            content_type="image/png",
            size=9,
        ),
    )

    assert updated.id == "ref-1"
    assert updated.filename == "updated.png"
    assert updated.mime_type == "image/png"
    assert updated.created_at == now
    stored = ref_repo.get_by_id("ref-1")
    assert stored is not None
    assert stored.filename == "updated.png"
    assert stored.created_at == now
    assert storage.written == ["inventories/inv-1/visual_references/ref-1.png"]
    assert storage.deleted == ["inventories/inv-1/visual_references/ref-1.jpg"]


def test_replace_inventory_visual_reference_raises_when_reference_missing() -> None:
    now = datetime(2025, 4, 1, 12, 0, 0, tzinfo=timezone.utc)
    inv_repo = StubInventoryRepo()
    inv_repo.save(_inventory(now))
    ref_repo = StubVisualReferenceRepo()
    storage = StubArtifactStorage()

    use_case = ReplaceInventoryVisualReferenceUseCase(inv_repo, ref_repo, storage)
    with pytest.raises(InventoryVisualReferenceNotFoundError):
        use_case.execute(
            "inv-1",
            "missing",
            UploadedVisualReferenceFile(
                original_filename="updated.png",
                file_obj=BytesIO(b"new-image"),
                content_type="image/png",
                size=9,
            ),
        )
