"""
ListAisleAssets use case — v3.0 Épica 4.

Returns source assets for an aisle. Validates that the aisle exists and belongs to the inventory.
"""

from __future__ import annotations

from collections.abc import Sequence

from src.application.dto.access_principal import AccessPrincipal
from src.application.ports.repositories import AisleRepository, SourceAssetRepository
from src.application.services.inventory_access_policy import InventoryAccessPolicy
from src.domain.aisle.entities import Aisle
from src.domain.assets.entities import SourceAsset


class ListAisleAssetsUseCase:
    def __init__(
        self,
        aisle_repo: AisleRepository,
        asset_repo: SourceAssetRepository,
        access_policy: InventoryAccessPolicy,
    ) -> None:
        self._aisle_repo = aisle_repo
        self._asset_repo = asset_repo
        self._access_policy = access_policy

    def _aisle_or_raise(
        self,
        inventory_id: str,
        aisle_id: str,
        *,
        principal: AccessPrincipal,
    ) -> Aisle:
        return self._access_policy.require_aisle(inventory_id, aisle_id, principal)

    def execute(
        self,
        inventory_id: str,
        aisle_id: str,
        *,
        principal: AccessPrincipal,
    ) -> Sequence[SourceAsset]:
        self._aisle_or_raise(inventory_id, aisle_id, principal=principal)
        return self._asset_repo.list_by_aisle(aisle_id)

    def get_validated_aisle(
        self,
        inventory_id: str,
        aisle_id: str,
        *,
        principal: AccessPrincipal,
    ) -> Aisle:
        """Same inventory/aisle validation as ``execute``; returns the aisle row (e.g. HEIC normalized path)."""
        return self._aisle_or_raise(inventory_id, aisle_id, principal=principal)
