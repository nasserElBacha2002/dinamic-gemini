"""CLI — A5 legacy/default client+supplier backfill (manual, idempotent).

Usage:

  python -m src.backfill_legacy_client_supplier_defaults
"""

from __future__ import annotations

import sys

from src.application.use_cases.suppliers.backfill_legacy_client_supplier_defaults import (
    BackfillLegacyClientSupplierDefaultsUseCase,
)
from src.runtime.v3_deps import (
    get_aisle_repo,
    get_client_repo,
    get_client_supplier_repo,
    get_clock,
    get_inventory_repo,
)


def main() -> int:
    use_case = BackfillLegacyClientSupplierDefaultsUseCase(
        client_repo=get_client_repo(),
        client_supplier_repo=get_client_supplier_repo(),
        inventory_repo=get_inventory_repo(),
        aisle_repo=get_aisle_repo(),
        clock=get_clock(),
    )

    try:
        result = use_case.execute()
    except Exception as exc:
        print(f"Backfill failed: {exc}", file=sys.stderr)
        return 1

    print("Legacy/default client-supplier backfill completed.")
    print(
        "  Legacy client           : "
        f"{'created' if result.legacy_client_created else 'reused'} ({result.legacy_client_id})"
    )
    print(
        "  Legacy supplier         : "
        f"{'created' if result.legacy_supplier_created else 'reused'} ({result.legacy_supplier_id})"
    )
    print(f"  Inventories NULL before : {result.inventories_null_before}")
    print(f"  Inventories updated     : {result.inventories_updated}")
    print(f"  Inventories NULL after  : {result.inventories_null_after}")
    print(f"  Aisles NULL before      : {result.aisles_null_before}")
    print(f"  Aisles updated          : {result.aisles_updated}")
    print(f"  Aisles NULL after       : {result.aisles_null_after}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

