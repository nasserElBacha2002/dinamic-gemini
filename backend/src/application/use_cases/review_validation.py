"""
Shared validation helpers for review use cases — v3.0 Épica 8.

Resolve inventory/aisle/position (and optionally product) with consistent error semantics.
Run-scoped reviews: ``job_id`` on the request must match ``positions.job_id`` when the row is
run-scoped; legacy rows require no job id. ``aisles.operational_job_id`` is not used for authorization.
"""

from __future__ import annotations

from typing import Optional

from src.application.errors import (
    AisleNotFoundError,
    InventoryNotFoundError,
    PositionDeletedError,
    PositionNotFoundError,
    ProductNotFoundError,
)
from src.application.services.aisle_inventory_scope import require_aisle_scoped_to_inventory
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


def _normalize_job_id_param(raw: Optional[str]) -> Optional[str]:
    if raw is None:
        return None
    s = str(raw).strip()
    return s if s else None


def _storage_job_id_on_position(position: Position) -> Optional[str]:
    """Effective job id on the position row: ``None`` = legacy ``job_id IS NULL``."""
    return _normalize_job_id_param(position.job_id)


def ensure_review_job_matches_position(request_job_id: Optional[str], position: Position) -> None:
    """Ensure POST ``job_id`` matches the storage row (run-scoped vs legacy).

    Rules:
    - Legacy row (``position.job_id`` unset): ``request_job_id`` must be omitted/empty (no claim of a run).
    - Run-scoped row: ``request_job_id`` is required and must equal ``position.job_id``.

    Raises:
        ValueError: semantic mismatch (HTTP 422 from route layer).
    """
    req = _normalize_job_id_param(request_job_id)
    row = _storage_job_id_on_position(position)
    if row is None:
        if req is not None:
            raise ValueError("job_id must be omitted for legacy positions (storage job_id IS NULL)")
        return
    if req is None:
        raise ValueError("job_id is required for run-scoped positions")
    if req != row:
        raise ValueError("job_id does not match the position's storage job_id")


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
    aisle = require_aisle_scoped_to_inventory(
        aisle_repo,
        inventory_id=inventory_id,
        aisle_id=aisle_id,
        detail_style="strict",
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
    """Review edits are allowed for both legacy and run-scoped rows under the same aisle.

    Promotion to operational remains a separate concern. Review actions stay attached to the
    concrete ``position_id`` row being edited, so trial/run-scoped corrections do not mutate
    canonical rows implicitly.
    """
    _ = aisle
    _ = position


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


def storage_job_id_for_review_audit(position: Position) -> Optional[str]:
    """Persist the run id on ``review_actions`` (null for legacy rows)."""
    return _storage_job_id_on_position(position)
