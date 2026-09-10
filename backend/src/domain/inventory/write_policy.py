"""Authoritative inventory write policy for late-write channels.

Writable statuses match Phase 3 position materialization: draft, processing,
and in_review. Completed and failed inventories reject mutation.
"""

from __future__ import annotations

from collections.abc import Iterable
from enum import Enum

from src.domain.inventory.entities import Inventory, InventoryStatus


class InventoryWriteDenialCode(str, Enum):
    INVENTORY_NOT_FOUND = "INVENTORY_NOT_FOUND"
    INVENTORY_NOT_WRITABLE = "INVENTORY_NOT_WRITABLE"
    INVENTORY_CLOSED = "INVENTORY_CLOSED"
    LATE_SYNC_REJECTED = "LATE_SYNC_REJECTED"


WRITABLE_INVENTORY_STATUSES: frozenset[InventoryStatus] = frozenset(
    {
        InventoryStatus.DRAFT,
        InventoryStatus.PROCESSING,
        InventoryStatus.IN_REVIEW,
    }
)

# Terminal / non-editable statuses for operator-facing messaging.
CLOSED_INVENTORY_STATUSES: frozenset[InventoryStatus] = frozenset(
    {
        InventoryStatus.COMPLETED,
        InventoryStatus.FAILED,
    }
)


class InventoryNotWritableError(Exception):
    """Raised when a late write targets a non-editable inventory."""

    def __init__(
        self,
        code: InventoryWriteDenialCode | str,
        detail: str,
        *,
        inventory_id: str | None = None,
        inventory_status: str | None = None,
    ) -> None:
        super().__init__(detail)
        self.code = code.value if isinstance(code, InventoryWriteDenialCode) else str(code)
        self.detail = detail
        self.inventory_id = inventory_id
        self.inventory_status = inventory_status


def coerce_inventory_status(status: InventoryStatus | str) -> InventoryStatus:
    if isinstance(status, InventoryStatus):
        return status
    normalized = str(status or "").strip().lower()
    try:
        return InventoryStatus(normalized)
    except ValueError as exc:
        raise InventoryNotWritableError(
            InventoryWriteDenialCode.INVENTORY_NOT_WRITABLE,
            f"Unknown inventory status {status!r}",
            inventory_status=normalized or None,
        ) from exc


def is_inventory_status_writable(status: InventoryStatus | str) -> bool:
    return coerce_inventory_status(status) in WRITABLE_INVENTORY_STATUSES


def inventory_write_denial_code(status: InventoryStatus | str) -> InventoryWriteDenialCode:
    coerced = coerce_inventory_status(status)
    if coerced in CLOSED_INVENTORY_STATUSES:
        return InventoryWriteDenialCode.INVENTORY_CLOSED
    return InventoryWriteDenialCode.INVENTORY_NOT_WRITABLE


def require_inventory_writable(
    inventory: Inventory | None,
    *,
    inventory_id: str | None = None,
    late_sync: bool = False,
) -> Inventory:
    """Return inventory when writable; otherwise raise ``InventoryNotWritableError``."""
    if inventory is None:
        raise InventoryNotWritableError(
            InventoryWriteDenialCode.INVENTORY_NOT_FOUND,
            f"Inventory {inventory_id or '<unknown>'} not found",
            inventory_id=inventory_id,
        )
    if inventory.is_deleted:
        raise InventoryNotWritableError(
            InventoryWriteDenialCode.INVENTORY_NOT_WRITABLE,
            f"Inventory {inventory.id} is deleted and not writable",
            inventory_id=inventory.id,
            inventory_status=inventory.status.value,
        )
    if not is_inventory_status_writable(inventory.status):
        denial = (
            InventoryWriteDenialCode.LATE_SYNC_REJECTED
            if late_sync
            else inventory_write_denial_code(inventory.status)
        )
        raise InventoryNotWritableError(
            denial,
            (
                f"Inventory {inventory.id} status {inventory.status.value!r} "
                "does not allow writes"
            ),
            inventory_id=inventory.id,
            inventory_status=inventory.status.value,
        )
    return inventory


def writable_status_values() -> frozenset[str]:
    return frozenset(status.value for status in WRITABLE_INVENTORY_STATUSES)


def assert_status_in_writable_set(
    status: InventoryStatus | str,
    *,
    inventory_id: str | None = None,
    allowed: Iterable[InventoryStatus] | None = None,
) -> None:
    allowed_set = frozenset(allowed) if allowed is not None else WRITABLE_INVENTORY_STATUSES
    coerced = coerce_inventory_status(status)
    if coerced not in allowed_set:
        raise InventoryNotWritableError(
            inventory_write_denial_code(coerced),
            (
                f"Inventory {inventory_id or '<unknown>'} status {coerced.value!r} "
                "does not allow writes"
            ),
            inventory_id=inventory_id,
            inventory_status=coerced.value,
        )
