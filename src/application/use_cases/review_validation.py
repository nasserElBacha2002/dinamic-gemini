"""
Shared validation helpers for review use cases — v3.0 Épica 8.

Resolve inventory/aisle/position (and optionally product) with consistent error semantics.
Use cases call these to avoid duplicating the same validation flow.
"""

from __future__ import annotations

from src.application.errors import (
    AisleNotFoundError,
    InventoryNotFoundError,
    PositionDeletedError,
    PositionNotFoundError,
    ProductNotFoundError,
)
from src.application.ports.repositories import (
    AisleRepository,
    InventoryRepository,
    PositionRepository,
    ProductRecordRepository,
)
from src.domain.positions.entities import Position, PositionStatus
from src.domain.products.entities import ProductRecord


def ensure_position_not_deleted(position: Position) -> None:
    """Raise PositionDeletedError if the position is already logically deleted."""
    if position.status == PositionStatus.DELETED:
        raise PositionDeletedError(
            f"Position {position.id} is already deleted; review actions are not allowed on deleted positions"
        )


def resolve_position(
    inventory_repo: InventoryRepository,
    aisle_repo: AisleRepository,
    position_repo: PositionRepository,
    inventory_id: str,
    aisle_id: str,
    position_id: str,
) -> Position:
    """Resolve inventory, aisle, and position; ensure hierarchy is valid. Returns position. Raises if not found or mismatch."""
    inv = inventory_repo.get_by_id(inventory_id)
    if inv is None:
        raise InventoryNotFoundError(f"Inventory not found: {inventory_id}")
    aisle = aisle_repo.get_by_id(aisle_id)
    if aisle is None:
        raise AisleNotFoundError(f"Aisle not found: {aisle_id}")
    if aisle.inventory_id != inventory_id:
        raise AisleNotFoundError(
            f"Aisle {aisle_id} does not belong to inventory {inventory_id}"
        )
    position = position_repo.get_by_id(position_id)
    if position is None:
        raise PositionNotFoundError(f"Position not found: {position_id}")
    if position.aisle_id != aisle_id:
        raise PositionNotFoundError(
            f"Position {position_id} does not belong to aisle {aisle_id}"
        )
    return position


def resolve_product_for_position(
    product_repo: ProductRecordRepository,
    position_id: str,
    product_id: str,
) -> ProductRecord:
    """Resolve product and ensure it belongs to the given position. Returns product. Raises if not found or mismatch."""
    product = product_repo.get_by_id(product_id)
    if product is None:
        raise ProductNotFoundError(f"Product not found: {product_id}")
    if product.position_id != position_id:
        raise ProductNotFoundError(
            f"Product {product_id} does not belong to position {position_id}"
        )
    return product
