"""
Unit tests for MemoryInventoryVisualReferenceRepository — v3.2.4.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.database.sqlserver import now_utc
from src.domain.inventory.visual_reference import InventoryVisualReference
from src.infrastructure.repositories.memory_inventory_visual_reference_repository import (
    MemoryInventoryVisualReferenceRepository,
)


def test_save_and_list_by_inventory() -> None:
    repo = MemoryInventoryVisualReferenceRepository()
    now = now_utc()
    ref = InventoryVisualReference(
        id="ref-1",
        inventory_id="inv-1",
        filename="label.png",
        storage_path="inventories/inv-1/visual_references/ref-1.png",
        mime_type="image/png",
        file_size=1024,
        created_at=now,
    )
    repo.create(ref)
    listed = repo.list_by_inventory("inv-1")
    assert len(listed) == 1
    assert listed[0].id == "ref-1"
    assert listed[0].filename == "label.png"
    assert listed[0].storage_path == ref.storage_path


def test_list_by_inventory_empty_when_none() -> None:
    repo = MemoryInventoryVisualReferenceRepository()
    assert list(repo.list_by_inventory("inv-any")) == []


def test_multiple_references_same_inventory() -> None:
    repo = MemoryInventoryVisualReferenceRepository()
    base = datetime(2025, 3, 1, 12, 0, 0, tzinfo=timezone.utc)
    for i in range(3):
        ref = InventoryVisualReference(
            id=f"ref-{i}",
            inventory_id="inv-1",
            filename=f"img{i}.png",
            storage_path=f"inventories/inv-1/visual_references/ref-{i}.png",
            mime_type="image/png",
            file_size=100 * (i + 1),
            created_at=base.replace(minute=base.minute + i),
        )
        repo.create(ref)
    listed = repo.list_by_inventory("inv-1")
    assert len(listed) == 3
    assert [r.id for r in listed] == ["ref-0", "ref-1", "ref-2"]


def test_isolation_across_inventories() -> None:
    repo = MemoryInventoryVisualReferenceRepository()
    now = now_utc()
    repo.create(
        InventoryVisualReference(
            id="r1",
            inventory_id="inv-A",
            filename="a.png",
            storage_path="inventories/inv-A/visual_references/r1.png",
            mime_type="image/png",
            file_size=100,
            created_at=now,
        )
    )
    repo.create(
        InventoryVisualReference(
            id="r2",
            inventory_id="inv-B",
            filename="b.jpg",
            storage_path="inventories/inv-B/visual_references/r2.jpg",
            mime_type="image/jpeg",
            file_size=200,
            created_at=now,
        )
    )
    list_a = repo.list_by_inventory("inv-A")
    list_b = repo.list_by_inventory("inv-B")
    assert len(list_a) == 1 and list_a[0].inventory_id == "inv-A"
    assert len(list_b) == 1 and list_b[0].inventory_id == "inv-B"


def test_duplicate_create_fails() -> None:
    repo = MemoryInventoryVisualReferenceRepository()
    now = now_utc()
    ref = InventoryVisualReference(
        id="dup-1",
        inventory_id="inv-1",
        filename="a.png",
        storage_path="inventories/inv-1/visual_references/dup-1.png",
        mime_type="image/png",
        file_size=10,
        created_at=now,
    )
    repo.create(ref)
    with pytest.raises(ValueError):
        repo.create(ref)
