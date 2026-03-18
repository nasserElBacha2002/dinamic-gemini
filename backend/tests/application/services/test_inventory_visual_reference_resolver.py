"""Tests for InventoryVisualReferenceResolver — v3.2.4."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Optional, Sequence

import pytest

from src.application.errors import InventoryNotFoundError
from src.application.ports.repositories import InventoryRepository, InventoryVisualReferenceRepository
from src.application.services.inventory_visual_reference_resolver import InventoryVisualReferenceResolver
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.domain.inventory.visual_reference import InventoryVisualReference


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
        self._store[reference.id] = reference

    def create_many(self, references: Sequence[InventoryVisualReference]) -> None:
        for r in references:
            self._store[r.id] = r

    def list_by_inventory(self, inventory_id: str) -> Sequence[InventoryVisualReference]:
        refs = [r for r in self._store.values() if r.inventory_id == inventory_id]
        refs.sort(key=lambda r: (r.created_at, r.id))
        return refs


def _inventory() -> Inventory:
    now = datetime(2025, 3, 15, 12, 0, 0, tzinfo=timezone.utc)
    return Inventory(
        id="inv-1",
        name="Inv",
        status=InventoryStatus.DRAFT,
        created_at=now,
        updated_at=now,
    )


def test_resolver_returns_empty_list_when_no_references() -> None:
    inv_repo = StubInventoryRepo()
    inv_repo.save(_inventory())
    ref_repo = StubVisualReferenceRepo()
    resolver = InventoryVisualReferenceResolver(inv_repo, ref_repo)

    result = resolver.resolve_for_inventory("inv-1")
    assert result == []


def test_resolver_maps_references_and_preserves_order() -> None:
    inv_repo = StubInventoryRepo()
    inv_repo.save(_inventory())
    ref_repo = StubVisualReferenceRepo()
    now = datetime(2025, 3, 15, 12, 0, 0, tzinfo=timezone.utc)
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
    resolver = InventoryVisualReferenceResolver(inv_repo, ref_repo)

    result = resolver.resolve_for_inventory("inv-1")
    assert [r.reference_id for r in result] == ["r0", "r1", "r2"]
    assert all(r.role == "inventory_reference" for r in result)
    assert all(r.source_path.endswith(f"{rid}.jpg") for r, rid in zip(result, ["r0", "r1", "r2"]))


def test_resolver_raises_when_inventory_not_found() -> None:
    inv_repo = StubInventoryRepo()
    ref_repo = StubVisualReferenceRepo()
    resolver = InventoryVisualReferenceResolver(inv_repo, ref_repo)

    with pytest.raises(InventoryNotFoundError):
        resolver.resolve_for_inventory("missing")

