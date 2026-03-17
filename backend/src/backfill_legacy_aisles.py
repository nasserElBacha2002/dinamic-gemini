"""
CLI entrypoint for v3.2.3.E4 — Backfill / recompute legacy aisles.

Usage examples:

  python -m src.backfill_legacy_aisles --inventory-id INV123
  python -m src.backfill_legacy_aisles --aisle-id A1 --aisle-id A2
  python -m src.backfill_legacy_aisles --all-aisles
"""

from __future__ import annotations

import argparse
import sys

from src.application.use_cases.backfill_legacy_aisles import (
    BackfillLegacyAislesCommand,
    BackfillLegacyAislesUseCase,
)
from src.runtime.v3_deps import (
    get_aisle_repo,
    get_inventory_repo,
    get_recompute_consolidated_counts_use_case,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="v3.2.3 — Backfill / recompute consolidated counts for legacy aisles.",
    )
    parser.add_argument(
        "--inventory-id",
        type=str,
        help="Inventory whose aisles should be recomputed.",
    )
    parser.add_argument(
        "--aisle-id",
        action="append",
        dest="aisle_ids",
        help="Explicit aisle id to recompute (can be repeated).",
    )
    parser.add_argument(
        "--all-aisles",
        action="store_true",
        help="Recompute all aisles for all inventories (use with care).",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()

    inventory_id = (args.inventory_id or "").strip() or None
    aisle_ids = args.aisle_ids or None
    all_aisles = bool(args.all_aisles)

    # Enforce clear targeting semantics at the CLI level before delegating.
    modes = [
        bool(aisle_ids),
        inventory_id is not None,
        all_aisles,
    ]
    if sum(1 for m in modes if m) == 0:
        print(
            "Error: must specify exactly one of --inventory-id, --aisle-id, or --all-aisles",
            file=sys.stderr,
        )
        return 2
    if sum(1 for m in modes if m) > 1:
        print(
            "Error: choose a single targeting mode: "
            "--inventory-id OR one or more --aisle-id OR --all-aisles",
            file=sys.stderr,
        )
        return 2

    inv_repo = get_inventory_repo()
    aisle_repo = get_aisle_repo()
    recompute_uc = get_recompute_consolidated_counts_use_case()

    uc = BackfillLegacyAislesUseCase(
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        recompute_uc=recompute_uc,
    )
    cmd = BackfillLegacyAislesCommand(
        inventory_id=inventory_id,
        aisle_ids=aisle_ids,
        all_aisles=all_aisles,
    )
    try:
        result = uc.execute(cmd)
    except ValueError as e:
        # Propagate configuration/targeting errors as explicit non-zero exit with message.
        print(f"Error: {e}", file=sys.stderr)
        return 2

    print("Backfill completed.")
    print(f"  Aisles scanned     : {result.total_aisles_scanned}")
    print(f"  Aisles recomputed  : {result.total_aisles_recomputed}")
    print(f"  Successes          : {result.total_successes}")
    print(f"  Failures           : {result.total_failures}")
    if result.aisle_results:
        print("Per-aisle results:")
        for r in result.aisle_results:
            status = "OK" if r.success else "FAIL"
            print(
                f"  - inv={r.inventory_id or '?'} aisle={r.aisle_id} "
                f"status={status} raw={r.raw_count} norm={r.normalized_count} "
                f"final={r.final_count} updated_products={r.product_records_updated}"
                + (f" error={r.error_message}" if r.error_message and not r.success else "")
            )

    # Non-zero exit code when there were failures.
    return 0 if result.total_failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

