"""
ListAisleAssets use case — v3.0 Épica 4.

Returns source assets for an aisle. Validates that the aisle exists and belongs to the inventory.
"""

from __future__ import annotations

from typing import Sequence

from src.application.errors import AisleNotFoundError
from src.application.ports.repositories import AisleRepository, SourceAssetRepository
from src.domain.assets.entities import SourceAsset


class ListAisleAssetsUseCase:
    def __init__(
        self,
        aisle_repo: AisleRepository,
        asset_repo: SourceAssetRepository,
    ) -> None:
        self._aisle_repo = aisle_repo
        self._asset_repo = asset_repo

    def execute(self, inventory_id: str, aisle_id: str) -> Sequence[SourceAsset]:
        aisle = self._aisle_repo.get_by_id(aisle_id)
        if aisle is None:
            raise AisleNotFoundError(f"Aisle not found: {aisle_id}")
        if aisle.inventory_id != inventory_id:
            raise AisleNotFoundError(
                f"Aisle {aisle_id} does not belong to inventory {inventory_id}"
            )
        return self._asset_repo.list_by_aisle(aisle_id)
