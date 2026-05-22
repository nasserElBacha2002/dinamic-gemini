"""
One-shot maintenance: refresh persisted ``inventories.status`` from aisle aggregates.

Run after deploy to correct rows that were stuck (e.g. draft / in_review) before
reconciliation hooks existed. Safe to re-run: only updates when derived status differs.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.application.ports.repositories import InventoryRepository
from src.application.services.inventory_status_reconciler import InventoryStatusReconciler


@dataclass(frozen=True)
class BackfillInventoryStatusesResult:
    inventories_scanned: int
    inventories_updated: int


class BackfillInventoryStatusesUseCase:
    def __init__(
        self,
        inventory_repo: InventoryRepository,
        status_reconciler: InventoryStatusReconciler,
    ) -> None:
        self._inventory_repo = inventory_repo
        self._status_reconciler = status_reconciler

    def execute(self) -> BackfillInventoryStatusesResult:
        scanned = 0
        updated = 0
        for inv in self._inventory_repo.list_all():
            scanned += 1
            if self._status_reconciler.reconcile(inv.id):
                updated += 1
        return BackfillInventoryStatusesResult(
            inventories_scanned=scanned,
            inventories_updated=updated,
        )
