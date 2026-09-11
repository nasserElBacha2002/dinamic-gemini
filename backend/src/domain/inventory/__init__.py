"""V3.0 Inventory entity (Documento técnico §7.1)."""

from src.domain.inventory.derive_status_from_aisles import (
    derive_inventory_status_from_aisles,
    derive_inventory_status_with_reason,
)
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.domain.inventory.write_policy import (
    CLOSED_INVENTORY_STATUSES,
    WRITABLE_INVENTORY_STATUSES,
    InventoryNotWritableError,
    InventoryWriteDenialCode,
    is_inventory_status_writable,
    require_inventory_writable,
)

__all__ = [
    "CLOSED_INVENTORY_STATUSES",
    "Inventory",
    "InventoryNotWritableError",
    "InventoryStatus",
    "InventoryWriteDenialCode",
    "WRITABLE_INVENTORY_STATUSES",
    "derive_inventory_status_from_aisles",
    "derive_inventory_status_with_reason",
    "is_inventory_status_writable",
    "require_inventory_writable",
]
