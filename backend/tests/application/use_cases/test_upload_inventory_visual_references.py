"""Tests for UploadInventoryVisualReferencesUseCase and ListInventoryVisualReferencesUseCase — v3.2.4."""

from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from typing import Dict, Optional, Sequence

import pytest

from src.application.errors import (
    EmptyUploadError,
    InventoryNotFoundError,
    MaxInventoryVisualReferencesExceededError,
    UnsupportedAssetTypeError,
    ZeroByteFileError,
)
from src.application.ports.repositories import InventoryRepository, InventoryVisualReferenceRepository
from src.application.ports.services import ArtifactStorage
from src.application.ports.clock import Clock
from src.application.use_cases.upload_inventory_visual_references import (
    ALLOWED_MIME_TYPES,
    ListInventoryVisualReferencesUseCase,
    MAX_REFERENCES_PER_INVENTORY,
    UploadInventoryVisualReferencesUseCase,
    UploadedVisualReferenceFile,
)
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.domain.inventory.visual_reference import InventoryVisualReference
from src.infrastructure.storage.artifact_store import StoredArtifact


class FixedClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


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

    def create(self, reference: InventoryVisualReference) -> None:
        if reference.id in self._store:
            raise ValueError("duplicate id")
        self._store[reference.id] = reference

    def create_many(self, references: Sequence[InventoryVisualReference]) -> None:
        # Atomic semantics for stub: pre-check duplicates, then insert.
        for r in references:
            if r.id in self._store:
                raise ValueError("duplicate id")
        for r in references:
            self._store[r.id] = r

    def list_by_inventory(self, inventory_id: str) -> Sequence[InventoryVisualReference]:
        refs = [r for r in self._store.values() if r.inventory_id == inventory_id]
        refs.sort(key=lambda r: (r.created_at, r.id))
        return refs


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
            storage_bucket="bucket-b",
            storage_key=path,
            content_type=content_type,
            file_size_bytes=len(content),
            etag="etag-ref",
        )

    def delete_file(self, path: str) -> None:
        self._deleted.append(path)


class PrefixedKeyArtifactStorage(StubArtifactStorage):
    def put_object(self, path: str, file_obj: BytesIO, content_type: str) -> StoredArtifact:
        content = file_obj.read()
        self._written.append((path, content, content_type))
        return StoredArtifact(
            storage_provider="s3",
            storage_bucket="bucket-b",
            storage_key=f"v3/{path}",
            content_type=content_type,
            file_size_bytes=len(content),
            etag="etag-ref",
        )


class FailingAfterFirstCreateRepo(StubVisualReferenceRepo):
    """Repo that fails on create_many() to simulate DB failure mid-batch."""

    def create_many(self, references: Sequence[InventoryVisualReference]) -> None:
        raise RuntimeError("simulated db failure")


def _inventory(now: datetime) -> Inventory:
    return Inventory(
        id="inv-1",
        name="Test inv",
        status=InventoryStatus.DRAFT,
        created_at=now,
        updated_at=now,
    )


def test_upload_inventory_visual_references_creates_references_and_writes_files() -> None:
    now = datetime(2025, 3, 10, 12, 0, 0, tzinfo=timezone.utc)
    inv_repo = StubInventoryRepo()
    inv_repo.save(_inventory(now))
    ref_repo = StubVisualReferenceRepo()
    storage = StubArtifactStorage()
    clock = FixedClock(now)

    use_case = UploadInventoryVisualReferencesUseCase(
        inventory_repo=inv_repo,
        reference_repo=ref_repo,
        artifact_storage=storage,
        clock=clock,
    )
    files = [
        UploadedVisualReferenceFile("ref1.jpg", BytesIO(b"jpeg-data"), "image/jpeg", size=9),
        UploadedVisualReferenceFile("ref2.png", BytesIO(b"png-data"), "image/png", size=8),
    ]
    created = use_case.execute("inv-1", files)

    assert len(created) == 2
    assert all(r.inventory_id == "inv-1" for r in created)
    assert created[0].file_size == 9
    assert created[1].file_size == 8
    assert all(r.storage_provider == "s3" for r in created)
    assert all(r.storage_bucket == "bucket-b" for r in created)
    assert all((r.storage_key or "").startswith("inventories/inv-1/visual_references/") for r in created)
    assert all((r.storage_path or "").startswith("inventories/inv-1/visual_references/") for r in created)
    assert len(storage._written) == 2
    paths = [p for (p, _, _) in storage._written]
    assert paths[0].startswith("inventories/inv-1/visual_references/")
    assert paths[1].startswith("inventories/inv-1/visual_references/")


def test_upload_inventory_visual_references_raises_when_inventory_not_found() -> None:
    now = datetime(2025, 3, 10, 12, 0, 0, tzinfo=timezone.utc)
    inv_repo = StubInventoryRepo()
    ref_repo = StubVisualReferenceRepo()
    storage = StubArtifactStorage()

    use_case = UploadInventoryVisualReferencesUseCase(
        inventory_repo=inv_repo,
        reference_repo=ref_repo,
        artifact_storage=storage,
        clock=FixedClock(now),
    )
    files = [UploadedVisualReferenceFile("x.jpg", BytesIO(b"x"), "image/jpeg", size=1)]

    with pytest.raises(InventoryNotFoundError):
        use_case.execute("inv-unknown", files)


def test_upload_inventory_visual_references_raises_when_empty_files() -> None:
    now = datetime(2025, 3, 10, 12, 0, 0, tzinfo=timezone.utc)
    inv_repo = StubInventoryRepo()
    inv_repo.save(_inventory(now))
    ref_repo = StubVisualReferenceRepo()
    storage = StubArtifactStorage()

    use_case = UploadInventoryVisualReferencesUseCase(
        inventory_repo=inv_repo,
        reference_repo=ref_repo,
        artifact_storage=storage,
        clock=FixedClock(now),
    )

    with pytest.raises(EmptyUploadError, match="At least one file"):
        use_case.execute("inv-1", [])


def test_upload_inventory_visual_references_raises_when_unsupported_mime_type() -> None:
    now = datetime(2025, 3, 10, 12, 0, 0, tzinfo=timezone.utc)
    inv_repo = StubInventoryRepo()
    inv_repo.save(_inventory(now))
    ref_repo = StubVisualReferenceRepo()
    storage = StubArtifactStorage()

    use_case = UploadInventoryVisualReferencesUseCase(
        inventory_repo=inv_repo,
        reference_repo=ref_repo,
        artifact_storage=storage,
        clock=FixedClock(now),
    )
    files = [UploadedVisualReferenceFile("doc.pdf", BytesIO(b"pdf"), "application/pdf", size=3)]

    with pytest.raises(UnsupportedAssetTypeError):
        use_case.execute("inv-1", files)


def test_upload_inventory_visual_references_respects_max_references_per_inventory() -> None:
    now = datetime(2025, 3, 10, 12, 0, 0, tzinfo=timezone.utc)
    inv_repo = StubInventoryRepo()
    inv_repo.save(_inventory(now))
    ref_repo = StubVisualReferenceRepo()
    storage = StubArtifactStorage()
    clock = FixedClock(now)

    use_case = UploadInventoryVisualReferencesUseCase(
        inventory_repo=inv_repo,
        reference_repo=ref_repo,
        artifact_storage=storage,
        clock=clock,
    )

    # Pre-fill to max
    for i in range(MAX_REFERENCES_PER_INVENTORY):
        ref = InventoryVisualReference(
            id=f"r{i}",
            inventory_id="inv-1",
            filename=f"f{i}.jpg",
            storage_path=f"inventories/inv-1/visual_references/r{i}.jpg",
            mime_type="image/jpeg",
            file_size=10,
            created_at=now,
        )
        ref_repo.create(ref)

    files = [UploadedVisualReferenceFile("extra.jpg", BytesIO(b"x"), "image/jpeg", size=1)]
    with pytest.raises(MaxInventoryVisualReferencesExceededError, match="Maximum visual references exceeded"):
        use_case.execute("inv-1", files)


def test_upload_inventory_visual_references_raises_when_zero_byte_file() -> None:
    now = datetime(2025, 3, 10, 12, 0, 0, tzinfo=timezone.utc)
    inv_repo = StubInventoryRepo()
    inv_repo.save(_inventory(now))
    ref_repo = StubVisualReferenceRepo()
    storage = StubArtifactStorage()

    use_case = UploadInventoryVisualReferencesUseCase(
        inventory_repo=inv_repo,
        reference_repo=ref_repo,
        artifact_storage=storage,
        clock=FixedClock(now),
    )
    files = [UploadedVisualReferenceFile("empty.jpg", BytesIO(b""), "image/jpeg", size=0)]

    with pytest.raises(ZeroByteFileError, match="zero-byte"):
        use_case.execute("inv-1", files)
    assert len(storage._written) == 0


def test_upload_inventory_visual_references_invalid_mime_fails_before_any_write() -> None:
    """When second file has invalid mime, validation runs up front so no files are written."""
    now = datetime(2025, 3, 10, 12, 0, 0, tzinfo=timezone.utc)
    inv_repo = StubInventoryRepo()
    inv_repo.save(_inventory(now))
    ref_repo = StubVisualReferenceRepo()
    storage = StubArtifactStorage()

    use_case = UploadInventoryVisualReferencesUseCase(
        inventory_repo=inv_repo,
        reference_repo=ref_repo,
        artifact_storage=storage,
        clock=FixedClock(now),
    )
    files = [
        UploadedVisualReferenceFile("ok.jpg", BytesIO(b"ok"), "image/jpeg", size=2),
        UploadedVisualReferenceFile("bad.pdf", BytesIO(b"bad"), "application/pdf", size=3),
    ]

    with pytest.raises(UnsupportedAssetTypeError):
        use_case.execute("inv-1", files)
    assert len(storage._written) == 0
    assert len(ref_repo.list_by_inventory("inv-1")) == 0


def test_upload_inventory_visual_references_rolls_back_written_files_on_db_failure() -> None:
    """If a later DB create fails, previously written files in this request are best-effort deleted."""
    now = datetime(2025, 3, 10, 12, 0, 0, tzinfo=timezone.utc)
    inv_repo = StubInventoryRepo()
    inv_repo.save(_inventory(now))
    ref_repo = FailingAfterFirstCreateRepo()
    storage = StubArtifactStorage()

    use_case = UploadInventoryVisualReferencesUseCase(
        inventory_repo=inv_repo,
        reference_repo=ref_repo,
        artifact_storage=storage,
        clock=FixedClock(now),
    )
    files = [
        UploadedVisualReferenceFile("ref1.jpg", BytesIO(b"jpeg-data"), "image/jpeg", size=9),
        UploadedVisualReferenceFile("ref2.png", BytesIO(b"png-data"), "image/png", size=8),
    ]

    with pytest.raises(RuntimeError, match="simulated db failure"):
        use_case.execute("inv-1", files)
    assert len(storage._written) == 2
    written_paths = [p for (p, _, _) in storage._written]
    assert storage._deleted == list(reversed(written_paths))
    assert len(ref_repo.list_by_inventory("inv-1")) == 0


def test_upload_inventory_visual_references_rollback_uses_persisted_prefixed_storage_keys_verbatim() -> None:
    now = datetime(2025, 3, 10, 12, 0, 0, tzinfo=timezone.utc)
    inv_repo = StubInventoryRepo()
    inv_repo.save(_inventory(now))
    ref_repo = FailingAfterFirstCreateRepo()
    storage = PrefixedKeyArtifactStorage()

    use_case = UploadInventoryVisualReferencesUseCase(
        inventory_repo=inv_repo,
        reference_repo=ref_repo,
        artifact_storage=storage,
        clock=FixedClock(now),
    )
    files = [
        UploadedVisualReferenceFile("ref1.jpg", BytesIO(b"jpeg-data"), "image/jpeg", size=9),
        UploadedVisualReferenceFile("ref2.png", BytesIO(b"png-data"), "image/png", size=8),
    ]

    with pytest.raises(RuntimeError, match="simulated db failure"):
        use_case.execute("inv-1", files)
    written_paths = [f"v3/{p}" for (p, _, _) in storage._written]
    assert storage._deleted == list(reversed(written_paths))


def test_list_inventory_visual_references_returns_ordered_references() -> None:
    now = datetime(2025, 3, 10, 12, 0, 0, tzinfo=timezone.utc)
    inv_repo = StubInventoryRepo()
    inv_repo.save(_inventory(now))
    ref_repo = StubVisualReferenceRepo()

    for i in range(3):
        ref = InventoryVisualReference(
            id=f"r{i}",
            inventory_id="inv-1",
            filename=f"f{i}.jpg",
            storage_path=f"inventories/inv-1/visual_references/r{i}.jpg",
            mime_type="image/jpeg",
            file_size=10,
            created_at=now.replace(minute=now.minute + i),
        )
        ref_repo.create(ref)

    use_case = ListInventoryVisualReferencesUseCase(
        inventory_repo=inv_repo,
        reference_repo=ref_repo,
    )
    result = use_case.execute("inv-1")

    assert [r.id for r in result] == ["r0", "r1", "r2"]


def test_list_inventory_visual_references_ordering_deterministic_by_id_when_created_at_ties() -> None:
    """When created_at is equal, order by id ASC for full determinism."""
    now = datetime(2025, 3, 10, 12, 0, 0, tzinfo=timezone.utc)
    inv_repo = StubInventoryRepo()
    inv_repo.save(_inventory(now))
    ref_repo = StubVisualReferenceRepo()
    for ref_id in ("r-b", "r-a", "r-c"):
        ref = InventoryVisualReference(
            id=ref_id,
            inventory_id="inv-1",
            filename="f.jpg",
            storage_path="inventories/inv-1/visual_references/x.jpg",
            mime_type="image/jpeg",
            file_size=1,
            created_at=now,
        )
        ref_repo.create(ref)

    use_case = ListInventoryVisualReferencesUseCase(
        inventory_repo=inv_repo,
        reference_repo=ref_repo,
    )
    result = use_case.execute("inv-1")

    assert [r.id for r in result] == ["r-a", "r-b", "r-c"]


def test_list_inventory_visual_references_inventory_not_found() -> None:
    now = datetime(2025, 3, 10, 12, 0, 0, tzinfo=timezone.utc)
    inv_repo = StubInventoryRepo()
    ref_repo = StubVisualReferenceRepo()

    use_case = ListInventoryVisualReferencesUseCase(
        inventory_repo=inv_repo,
        reference_repo=ref_repo,
    )

    with pytest.raises(InventoryNotFoundError):
        use_case.execute("inv-unknown")

