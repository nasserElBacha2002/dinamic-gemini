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
    ReviewMutationNotAllowedError,
)
from src.application.ports.repositories import (
    AisleRepository,
    InventoryRepository,
    PositionRepository,
    ProductRecordRepository,
)
from src.domain.aisle.entities import Aisle
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


def ensure_position_review_mutable_for_aisle(aisle: Aisle, position: Position) -> None:
    """Allow mutations only on the operational slice: legacy null-null or ``job_id == operational_job_id``."""
    operational = aisle.operational_job_id
    row_job = position.job_id
    if operational is None:
        if row_job is not None:
            raise ReviewMutationNotAllowedError(
                "Review edits apply only to legacy positions (job_id IS NULL) for this aisle"
            )
        return
    if row_job != operational:
        raise ReviewMutationNotAllowedError(
            "Review edits apply only to positions from the aisle operational job"
        )


def load_aisle_and_ensure_review_mutable(
    aisle_repo: AisleRepository,
    aisle_id: str,
    position: Position,
) -> None:
    aisle = aisle_repo.get_by_id(aisle_id)
    if aisle is None:
        raise AisleNotFoundError(f"Aisle not found: {aisle_id}")
    ensure_position_review_mutable_for_aisle(aisle, position)


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


def resolve_single_product_for_position(
    product_repo: ProductRecordRepository,
    position_id: str,
) -> ProductRecord:
    """Resolve the single product for a position when the API operates at Result/position level.

    Assumes there is exactly one backing product record for the position.
    Raises ProductNotFoundError when no product exists and ValueError when more than one exists.
    """
    products = product_repo.list_by_position(position_id)
    if not products:
        raise ProductNotFoundError(f"No products found for position {position_id}")
    if len(products) > 1:
        raise ValueError(
            f"Ambiguous product for position {position_id}: multiple products exist"
        )
    return products[0]
