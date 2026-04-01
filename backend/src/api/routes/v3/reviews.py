"""v3 position review actions: confirm, update_quantity, update_sku, mark_unknown, delete_position."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from src.api.dependencies import (
    get_confirm_position_use_case,
    get_mark_position_unknown_use_case,
    get_update_product_quantity_use_case,
    get_update_product_sku_use_case,
    get_delete_position_use_case,
)
from src.api.schemas.position_schemas import ReviewActionRequest
from src.application.use_cases.confirm_position import ConfirmPositionUseCase
from src.application.use_cases.mark_position_unknown import MarkPositionUnknownUseCase
from src.application.use_cases.update_product_quantity import UpdateProductQuantityUseCase
from src.application.use_cases.update_product_sku import UpdateProductSkuUseCase
from src.application.use_cases.delete_position import DeletePositionUseCase

from .shared import (
    handle_confirm,
    handle_mark_unknown,
    handle_update_quantity,
    handle_update_sku,
    handle_delete_position,
)

router = APIRouter()


@router.post(
    "/{inventory_id}/aisles/{aisle_id}/positions/{position_id}/reviews",
    status_code=204,
)
def submit_review_action(
    inventory_id: str,
    aisle_id: str,
    position_id: str,
    body: ReviewActionRequest,
    confirm_uc: ConfirmPositionUseCase = Depends(get_confirm_position_use_case),
    mark_unknown_uc: MarkPositionUnknownUseCase = Depends(get_mark_position_unknown_use_case),
    update_quantity_uc: UpdateProductQuantityUseCase = Depends(get_update_product_quantity_use_case),
    update_sku_uc: UpdateProductSkuUseCase = Depends(get_update_product_sku_use_case),
    delete_uc: DeletePositionUseCase = Depends(get_delete_position_use_case),
) -> None:
    """Submit a manual review action (confirm, update_quantity, update_sku, mark_unknown, delete_position)."""
    if body.action_type == "confirm":
        handle_confirm(inventory_id, aisle_id, position_id, confirm_uc)
        return
    if body.action_type == "mark_unknown":
        handle_mark_unknown(inventory_id, aisle_id, position_id, mark_unknown_uc)
        return
    if body.action_type == "update_quantity":
        handle_update_quantity(inventory_id, aisle_id, position_id, body, update_quantity_uc)
        return
    if body.action_type == "update_sku":
        handle_update_sku(inventory_id, aisle_id, position_id, body, update_sku_uc)
        return
    if body.action_type == "delete_position":
        handle_delete_position(inventory_id, aisle_id, position_id, delete_uc)
        return
    raise HTTPException(status_code=422, detail=f"Unknown action_type: {body.action_type!r}")
