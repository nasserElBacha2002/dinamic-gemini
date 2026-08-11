"""
CLI — Reconcile ``inventories.status`` from aisle aggregates (one-shot maintenance).

Safe to run after deploy to fix historical rows; idempotent.

Usage:

  python -m src.backfill_inventory_status
  python -m src.backfill_inventory_status --detect-only
"""

from __future__ import annotations

import argparse
import sys

from src.application.services.inventory_status_reconciler import InventoryStatusReconciler
from src.application.use_cases.inventories.backfill_inventory_statuses import (
    BackfillInventoryStatusesUseCase,
)
from src.runtime.v3_deps import get_aisle_repo, get_clock, get_inventory_repo


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Detect or repair inventory status drift")
    parser.add_argument(
        "--detect-only",
        action="store_true",
        help="Report drift without writing (observability)",
    )
    args = parser.parse_args(argv)

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
    result = uc.execute(detect_only=args.detect_only)
    mode = "detect-only" if args.detect_only else "repair"
    print(f"Inventory status backfill completed ({mode}).")
    print(f"  Inventories scanned: {result.inventories_scanned}")
    print(f"  Inventories drifted: {result.inventories_drifted}")
    print(f"  Inventories updated: {result.inventories_updated}")
    for drift in result.drifts:
        print(
            f"  - {drift.entity_id}: {drift.stored_status} -> {drift.expected_status} "
            f"({drift.reason})"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
