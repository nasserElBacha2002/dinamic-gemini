"""SQL cursor helpers for inventory write policy within caller transactions."""

from __future__ import annotations

from datetime import datetime, timezone

from src.application.ports.sql_cursor import SqlCursorLike
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.domain.inventory.write_policy import require_inventory_writable

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)

_INVENTORY_LOCK_COLUMNS = "id, status, deleted_at"


def require_inventory_writable_on_cursor(
    cur: SqlCursorLike,
    inventory_id: str,
    *,
    late_sync: bool = False,
) -> Inventory:
    """Lock inventory row and enforce write policy in the caller's transaction."""
    inv_id = (inventory_id or "").strip()
    cur.execute(
        f"""
        SELECT {_INVENTORY_LOCK_COLUMNS}
        FROM inventories WITH (UPDLOCK, ROWLOCK)
        WHERE id = ?
        """,
        (inv_id,),
    )
    row = cur.fetchone()
    if row is None:
        inventory = None
    else:
        status_str = getattr(row, "status", "draft") or "draft"
        try:
            status = InventoryStatus(str(status_str).strip().lower())
        except ValueError:
            status = InventoryStatus.DRAFT
        inventory = Inventory(
            id=str(getattr(row, "id", inv_id)),
            name="",
            status=status,
            created_at=_EPOCH,
            updated_at=_EPOCH,
            deleted_at=getattr(row, "deleted_at", None),
        )
    return require_inventory_writable(
        inventory,
        inventory_id=inv_id or None,
        late_sync=late_sync,
    )


def default_require_inventory_writable_on_cursor(
    cur: SqlCursorLike,
    inventory_id: str,
) -> None:
    """Default checker passed to import finalize when no test override is supplied."""
    require_inventory_writable_on_cursor(cur, inventory_id)
