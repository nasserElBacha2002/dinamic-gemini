"""
Inventory-scoped aisle row validation (Phase 8).

Centralizes two historical error-detail patterns used across use cases:
- **strict**: missing aisle vs wrong-inventory produce different ``AisleNotFoundError`` messages.
- **merged**: missing or wrong-inventory both use the single "does not belong" message.
"""

from __future__ import annotations

from typing import Literal

from src.application.errors import AisleNotFoundError
from src.application.ports.repositories import AisleRepository
from src.domain.aisle.entities import Aisle

_AisleScopeDetailStyle = Literal["strict", "merged"]


def require_aisle_scoped_to_inventory(
    aisle_repo: AisleRepository,
    *,
    inventory_id: str,
    aisle_id: str,
    detail_style: _AisleScopeDetailStyle = "strict",
) -> Aisle:
    """Load ``aisle_id`` and ensure it belongs to ``inventory_id``.

    ``detail_style`` selects which historical exception messages to preserve.
    """
    aisle = aisle_repo.get_by_id(aisle_id)
    if detail_style == "strict":
        if aisle is None:
            raise AisleNotFoundError(f"Aisle not found: {aisle_id}")
        if aisle.inventory_id != inventory_id:
            raise AisleNotFoundError(
                f"Aisle {aisle_id} does not belong to inventory {inventory_id}"
            )
        return aisle
    if aisle is None or aisle.inventory_id != inventory_id:
        raise AisleNotFoundError(
            f"Aisle {aisle_id} does not belong to inventory {inventory_id}"
        )
    return aisle
