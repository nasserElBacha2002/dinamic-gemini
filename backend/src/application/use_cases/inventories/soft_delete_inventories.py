"""Bulk soft-delete inventories (logical delete via deleted_at)."""

from __future__ import annotations

from dataclasses import dataclass

from src.application.dto.access_principal import AccessPrincipal
from src.application.ports.clock import Clock
from src.application.ports.repositories import InventoryRepository
from src.domain.inventory.entities import Inventory


@dataclass(frozen=True)
class SoftDeleteInventoriesResult:
    deleted_ids: tuple[str, ...]
    already_deleted_ids: tuple[str, ...]
    not_found_ids: tuple[str, ...]


@dataclass(frozen=True)
class SoftDeleteInventoriesCommand:
    inventory_ids: tuple[str, ...]
    principal: AccessPrincipal


def _dedupe_preserve_order(ids: tuple[str, ...]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in ids:
        inventory_id = (raw or "").strip()
        if not inventory_id or inventory_id in seen:
            continue
        seen.add(inventory_id)
        out.append(inventory_id)
    return out


def _principal_may_access(inventory: Inventory, principal: AccessPrincipal) -> bool:
    if principal.is_platform:
        return True
    principal_client = (principal.client_id or "").strip() or None
    if principal_client is None:
        return False
    inv_client = (inventory.client_id or "").strip() or None
    return inv_client == principal_client


class SoftDeleteInventoriesUseCase:
    """Mark inventories as soft-deleted. Idempotent; does not cascade to children."""

    def __init__(
        self,
        inventory_repo: InventoryRepository,
        clock: Clock,
    ) -> None:
        self._inventory_repo = inventory_repo
        self._clock = clock

    def execute(self, command: SoftDeleteInventoriesCommand) -> SoftDeleteInventoriesResult:
        ids = _dedupe_preserve_order(command.inventory_ids)
        if not ids:
            raise ValueError("inventory_ids must not be empty")

        deleted: list[str] = []
        already: list[str] = []
        not_found: list[str] = []
        now = self._clock.now()
        actor = (command.principal.actor_id or "").strip() or None

        for inventory_id in ids:
            inventory = self._inventory_repo.get_by_id(inventory_id)
            if inventory is None or not _principal_may_access(inventory, command.principal):
                not_found.append(inventory_id)
                continue
            if inventory.is_deleted:
                already.append(inventory_id)
                continue
            changed = inventory.mark_deleted(now, deleted_by=actor)
            if not changed:
                already.append(inventory_id)
                continue
            self._inventory_repo.save(inventory)
            deleted.append(inventory_id)

        return SoftDeleteInventoriesResult(
            deleted_ids=tuple(deleted),
            already_deleted_ids=tuple(already),
            not_found_ids=tuple(not_found),
        )
