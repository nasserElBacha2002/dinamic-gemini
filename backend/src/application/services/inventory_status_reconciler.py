"""
Reconcile persisted inventory.status from aisle aggregates (v3).

Called after aisle lifecycle changes so list/detail APIs and status filters stay aligned
with operational reality without frontend overrides.
"""

from __future__ import annotations

from datetime import datetime

from src.application.ports.clock import Clock
from src.application.ports.repositories import AisleRepository, InventoryRepository
from src.application.services.inventory_aggregation_scope import scope_from_aisles
from src.domain.inventory.derive_status_from_aisles import derive_inventory_status_from_aisles
from src.domain.inventory.entities import Inventory, InventoryStatus


class InventoryStatusReconciler:
    def __init__(
        self,
        inventory_repo: InventoryRepository,
        aisle_repo: AisleRepository,
        clock: Clock,
    ) -> None:
        self._inventory_repo = inventory_repo
        self._aisle_repo = aisle_repo
        self._clock = clock

    def reconcile(self, inventory_id: str) -> bool:
        """Recompute status from active aisles and persist if it changed. Returns True if persisted.

        Inactive aisles are ignored so a soft-deactivated failed/pending aisle cannot keep the
        inventory stuck. With no active aisles, ``derive_inventory_status_from_aisles`` yields DRAFT.
        """
        inv = self._inventory_repo.get_by_id(inventory_id)
        if inv is None:
            return False
        scope = scope_from_aisles(self._aisle_repo.list_by_inventory(inventory_id))
        new_status = derive_inventory_status_from_aisles(scope.operational_aisles)
        if new_status == inv.status:
            return False
        now = self._clock.now()
        _apply_status_transition(inv, new_status, now)
        self._inventory_repo.save(inv)
        return True


def _apply_status_transition(inv: Inventory, new_status: InventoryStatus, now: datetime) -> None:
    prev = inv.status
    inv.status = new_status
    inv.updated_at = now
    if new_status == InventoryStatus.COMPLETED:
        if prev != InventoryStatus.COMPLETED and inv.completed_at is None:
            inv.completed_at = now
    elif prev == InventoryStatus.COMPLETED:
        inv.completed_at = None
