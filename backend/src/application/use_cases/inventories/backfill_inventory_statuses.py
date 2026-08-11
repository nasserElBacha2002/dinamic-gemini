"""
One-shot maintenance: refresh persisted ``inventories.status`` from aisle aggregates.

Run after deploy to correct rows that were stuck (e.g. draft / in_review) before
reconciliation hooks existed. Safe to re-run: only updates when derived status differs.

Supports detect-only mode for observability without writes.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.application.ports.repositories import InventoryRepository
from src.application.services.inventory_status_reconciler import (
    InventoryStatusDrift,
    InventoryStatusReconciler,
)


@dataclass(frozen=True)
class BackfillInventoryStatusesResult:
    inventories_scanned: int
    inventories_updated: int
    inventories_drifted: int
    drifts: tuple[InventoryStatusDrift, ...] = ()


class BackfillInventoryStatusesUseCase:
    def __init__(
        self,
        inventory_repo: InventoryRepository,
        status_reconciler: InventoryStatusReconciler,
    ) -> None:
        self._inventory_repo = inventory_repo
        self._status_reconciler = status_reconciler

    def execute(self, *, detect_only: bool = False) -> BackfillInventoryStatusesResult:
        """Scan all inventories; detect or repair status drift.

        Full scan is intentional for this one-shot / admin maintenance path (not a
        high-frequency worker). Callers that need detect-only observability pass
        ``detect_only=True`` (zero writes).
        """
        scanned = 0
        updated = 0
        drifts: list[InventoryStatusDrift] = []
        for inv in self._inventory_repo.list_all():
            scanned += 1
            if detect_only:
                drift = self._status_reconciler.detect(inv.id)
                if drift is not None:
                    drifts.append(drift)
                continue
            repaired = self._status_reconciler.repair(inv.id)
            if repaired is not None:
                updated += 1
                drifts.append(repaired)
        return BackfillInventoryStatusesResult(
            inventories_scanned=scanned,
            inventories_updated=updated,
            inventories_drifted=len(drifts),
            drifts=tuple(drifts),
        )
