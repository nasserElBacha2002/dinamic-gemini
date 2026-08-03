"""Shared tenant and result-scope resolution for position overrides."""

from __future__ import annotations

from dataclasses import dataclass

from src.application.dto.access_principal import AccessPrincipal
from src.application.ports.repositories import (
    AisleRepository,
    JobRepository,
    PositionRepository,
    ProductRecordRepository,
)
from src.application.position_override_errors import (
    PositionOverrideCrossTenantError,
    PositionOverrideResultNotActiveError,
    PositionOverrideResultNotFoundError,
)
from src.application.services.inventory_access_policy import InventoryAccessPolicy
from src.domain.inventory.entities import Inventory
from src.domain.positions.entities import PositionStatus


@dataclass(frozen=True)
class ScopeContext:
    inventory: Inventory
    client_id: str
    aisle_id: str
    source_asset_id: str | None = None


class PositionOverrideScopeResolver:
    def __init__(
        self,
        *,
        aisle_repo: AisleRepository,
        job_repo: JobRepository,
        position_repo: PositionRepository,
        product_repo: ProductRecordRepository,
        access_policy: InventoryAccessPolicy,
    ) -> None:
        self._aisle_repo = aisle_repo
        self._job_repo = job_repo
        self._position_repo = position_repo
        self._product_repo = product_repo
        self._access_policy = access_policy

    def resolve(
        self,
        *,
        inventory_id: str,
        job_id: str,
        result_id: str,
        principal: AccessPrincipal,
    ) -> ScopeContext:
        inventory = self._access_policy.require_inventory(inventory_id, principal)
        client_id = (inventory.client_id or "").strip()
        if not client_id:
            raise PositionOverrideCrossTenantError("Inventory has no client scope.")
        job = self._job_repo.get_by_id(job_id)
        product = self._product_repo.get_by_id(result_id)
        if product is None:
            raise PositionOverrideResultNotFoundError("Result not found.")
        position = self._position_repo.get_by_id(product.position_id)
        if position is None:
            raise PositionOverrideResultNotFoundError("Result not found.")
        aisle = self._aisle_repo.get_by_id(position.aisle_id)
        if (
            job is None
            or aisle is None
            or aisle.inventory_id != inventory_id
            or job.target_id != aisle.id
            or position.job_id != job_id
        ):
            raise PositionOverrideResultNotFoundError("Result not found in job scope.")
        if position.status is PositionStatus.DELETED:
            raise PositionOverrideResultNotActiveError("Result is not active.")
        return ScopeContext(
            inventory=inventory,
            client_id=client_id,
            aisle_id=aisle.id,
        )
