from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.domain.client_supplier.reference_image import SupplierReferenceImage
from src.infrastructure.repositories.memory_supplier_reference_image_repository import (
    MemorySupplierReferenceImageRepository,
)


def _image(
    image_id: str,
    supplier_id: str,
    created_at: datetime,
) -> SupplierReferenceImage:
    return SupplierReferenceImage(
        id=image_id,
        client_supplier_id=supplier_id,
        filename=f"{image_id}.jpg",
        storage_path=f"client_suppliers/{supplier_id}/reference_images/{image_id}.jpg",
        mime_type="image/jpeg",
        file_size=10,
        created_at=created_at,
        updated_at=created_at,
    )


def test_create_and_list_by_supplier_orders_by_created_at_then_id() -> None:
    repo = MemorySupplierReferenceImageRepository()
    now = datetime(2026, 5, 7, 12, 0, 0, tzinfo=timezone.utc)
    repo.create(_image("img-b", "sup-1", now))
    repo.create(_image("img-a", "sup-1", now))
    listed = repo.list_by_supplier("sup-1")
    assert [row.id for row in listed] == ["img-a", "img-b"]


def test_list_by_supplier_is_isolated() -> None:
    repo = MemorySupplierReferenceImageRepository()
    now = datetime(2026, 5, 7, 12, 0, 0, tzinfo=timezone.utc)
    repo.create(_image("img-1", "sup-1", now))
    repo.create(_image("img-2", "sup-2", now))
    assert [row.id for row in repo.list_by_supplier("sup-1")] == ["img-1"]
    assert [row.id for row in repo.list_by_supplier("sup-2")] == ["img-2"]


def test_duplicate_create_fails() -> None:
    repo = MemorySupplierReferenceImageRepository()
    now = datetime(2026, 5, 7, 12, 0, 0, tzinfo=timezone.utc)
    image = _image("img-1", "sup-1", now)
    repo.create(image)
    with pytest.raises(ValueError):
        repo.create(image)


def test_delete_is_idempotent() -> None:
    repo = MemorySupplierReferenceImageRepository()
    now = datetime(2026, 5, 7, 12, 0, 0, tzinfo=timezone.utc)
    repo.create(_image("img-1", "sup-1", now))
    repo.delete("img-1")
    repo.delete("img-1")
    assert repo.get_by_id("img-1") is None
