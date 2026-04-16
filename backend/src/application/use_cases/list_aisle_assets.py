"""
ListAisleAssets use case — v3.0 Épica 4.

Returns source assets for an aisle. Validates that the aisle exists and belongs to the inventory.
"""

from __future__ import annotations

from typing import Sequence

from src.application.services.aisle_inventory_scope import require_aisle_scoped_to_inventory
from src.application.ports.repositories import AisleRepository, SourceAssetRepository
from src.domain.aisle.entities import Aisle
from src.domain.assets.entities import SourceAsset


class ListAisleAssetsUseCase:
    def __init__(
        self,
        aisle_repo: AisleRepository,
        asset_repo: SourceAssetRepository,
    ) -> None:
        self._aisle_repo = aisle_repo
        self._asset_repo = asset_repo

    def _aisle_or_raise(self, inventory_id: str, aisle_id: str) -> Aisle:
        return require_aisle_scoped_to_inventory(
            self._aisle_repo,
            inventory_id=inventory_id,
            aisle_id=aisle_id,
            detail_style="strict",
        )

    def execute(self, inventory_id: str, aisle_id: str) -> Sequence[SourceAsset]:
        self._aisle_or_raise(inventory_id, aisle_id)
        return self._asset_repo.list_by_aisle(aisle_id)

    def get_validated_aisle(self, inventory_id: str, aisle_id: str) -> Aisle:
        """Same inventory/aisle validation as ``execute``; returns the aisle row (e.g. HEIC normalized path)."""
        return self._aisle_or_raise(inventory_id, aisle_id)
