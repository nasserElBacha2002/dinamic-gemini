"""Bulk soft-delete inventories (logical delete via deleted_at) — transactional tenant scope."""

from __future__ import annotations

from dataclasses import dataclass

from src.application.dto.access_principal import AccessPrincipal
from src.application.ports.clock import Clock
from src.application.ports.repositories import InventoryRepository

# Keep below SQL Server parameter limits (~2100) with headroom for UPDATE binds.
MAX_SOFT_DELETE_INVENTORY_IDS = 100


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


class SoftDeleteInventoriesUseCase:
    """Mark inventories as soft-deleted. Idempotent; does not cascade to children.

    Atomic tenant rule: repository ``soft_delete_many_for_scope`` runs authorize-all +
    writes in one unit of work (SQL transaction or memory lock). Any inaccessible id
    yields zero modifications.
    """

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
        if len(ids) > MAX_SOFT_DELETE_INVENTORY_IDS:
            raise ValueError(
                f"inventory_ids must contain at most {MAX_SOFT_DELETE_INVENTORY_IDS} items"
            )

        principal = command.principal
        allow_all = principal.is_platform
        scope_client: str | None = None
        if not allow_all:
            scope_client = (principal.client_id or "").strip() or None
            if scope_client is None:
                return SoftDeleteInventoriesResult(
                    deleted_ids=(),
                    already_deleted_ids=(),
                    not_found_ids=tuple(ids),
                )

        deleted, already, not_found = self._inventory_repo.soft_delete_many_for_scope(
            ids,
            allow_all_clients=allow_all,
            client_id=scope_client,
            deleted_at=self._clock.now(),
            deleted_by=(principal.actor_id or "").strip() or None,
        )
        return SoftDeleteInventoriesResult(
            deleted_ids=deleted,
            already_deleted_ids=already,
            not_found_ids=not_found,
        )
