"""Resolve inventory visual references into analysis context objects — v3.2.4."""

from __future__ import annotations

from typing import List

from src.application.errors import InventoryNotFoundError
from src.application.ports.repositories import (
    InventoryRepository,
    InventoryVisualReferenceRepository,
)
from src.pipeline.contracts.analysis_context import VisualReferenceContext


class InventoryVisualReferenceResolver:
    """Resolve inventory-owned visual references into VisualReferenceContext objects."""

    def __init__(
        self,
        inventory_repo: InventoryRepository,
        reference_repo: InventoryVisualReferenceRepository,
    ) -> None:
        self._inventory_repo = inventory_repo
        self._reference_repo = reference_repo

    def resolve_for_inventory(self, inventory_id: str) -> List[VisualReferenceContext]:
        inventory = self._inventory_repo.get_by_id(inventory_id)
        if inventory is None:
            raise InventoryNotFoundError(f"Inventory not found: {inventory_id}")

        refs = self._reference_repo.list_by_inventory(inventory_id)
        # Repository already guarantees deterministic ordering (created_at ASC, id ASC).
        return [
            VisualReferenceContext(
                reference_id=r.id,
                source_path=r.storage_path,
                mime_type=r.mime_type,
                created_at=r.created_at,
            )
            for r in refs
        ]

