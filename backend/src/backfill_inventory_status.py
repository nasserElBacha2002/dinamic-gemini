"""
CLI — Reconcile ``inventories.status`` from aisle aggregates (one-shot maintenance).

Safe to run after deploy to fix historical rows; idempotent.

Usage:

  python -m src.backfill_inventory_status
"""

from __future__ import annotations

import sys

from src.application.services.inventory_status_reconciler import InventoryStatusReconciler
from src.application.use_cases.inventories.backfill_inventory_statuses import (
    BackfillInventoryStatusesUseCase,
)
from src.runtime.v3_deps import get_aisle_repo, get_clock, get_inventory_repo


def main() -> int:
    inv_repo = get_inventory_repo()
    aisle_repo = get_aisle_repo()
    clock = get_clock()
    reconciler = InventoryStatusReconciler(
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        clock=clock,
    )
    uc = BackfillInventoryStatusesUseCase(
        inventory_repo=inv_repo,
        status_reconciler=reconciler,
    )
    result = uc.execute()
    print("Inventory status backfill completed.")
    print(f"  Inventories scanned: {result.inventories_scanned}")
    print(f"  Inventories updated: {result.inventories_updated}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
