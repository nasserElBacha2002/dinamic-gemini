"""v3 position review actions: confirm, corrections, mark_unknown, mark_image_mismatch, delete_position."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from src.api.dependencies import (
    get_confirm_position_use_case,
    get_delete_position_use_case,
    get_mark_position_image_mismatch_use_case,
    get_mark_position_unknown_use_case,
    get_update_position_code_use_case,
    get_update_product_quantity_use_case,
    get_update_product_sku_use_case,
)
from src.api.schemas.position_schemas import ReviewActionRequest
from src.application.use_cases.confirm_position import ConfirmPositionUseCase
from src.application.use_cases.delete_position import DeletePositionUseCase
from src.application.use_cases.mark_position_image_mismatch import MarkPositionImageMismatchUseCase
from src.application.use_cases.mark_position_unknown import MarkPositionUnknownUseCase
from src.application.use_cases.update_position_code import UpdatePositionCodeUseCase
from src.application.use_cases.update_product_quantity import UpdateProductQuantityUseCase
from src.application.use_cases.update_product_sku import UpdateProductSkuUseCase
from src.domain.reviews.entities import ReviewActionType

from .shared import (
    handle_confirm,
    handle_delete_position,
    handle_mark_image_mismatch,
    handle_mark_unknown,
    handle_update_position_code,
    handle_update_quantity,
    handle_update_sku,
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
    mark_image_mismatch_uc: MarkPositionImageMismatchUseCase = Depends(
        get_mark_position_image_mismatch_use_case
    ),
    update_quantity_uc: UpdateProductQuantityUseCase = Depends(
        get_update_product_quantity_use_case
    ),
    update_sku_uc: UpdateProductSkuUseCase = Depends(get_update_product_sku_use_case),
    update_pos_code_uc: UpdatePositionCodeUseCase = Depends(get_update_position_code_use_case),
    delete_uc: DeletePositionUseCase = Depends(get_delete_position_use_case),
) -> None:
    """Submit a manual review action (confirm, corrections, mark_unknown, mark_image_mismatch, delete_position)."""
    # Pydantic validates ``action_type`` as ``ReviewActionType`` (same wire strings as the domain enum).
    action = body.action_type
    if action == ReviewActionType.CONFIRM:
        handle_confirm(inventory_id, aisle_id, position_id, body.job_id, confirm_uc)
        return
    if action == ReviewActionType.MARK_UNKNOWN:
        handle_mark_unknown(inventory_id, aisle_id, position_id, body.job_id, mark_unknown_uc)
        return
    if action == ReviewActionType.MARK_IMAGE_MISMATCH:
        handle_mark_image_mismatch(
            inventory_id, aisle_id, position_id, body.job_id, mark_image_mismatch_uc
        )
        return
    if action == ReviewActionType.UPDATE_QUANTITY:
        handle_update_quantity(inventory_id, aisle_id, position_id, body, update_quantity_uc)
        return
    if action == ReviewActionType.UPDATE_SKU:
        handle_update_sku(inventory_id, aisle_id, position_id, body, update_sku_uc)
        return
    if action == ReviewActionType.UPDATE_POSITION_CODE:
        handle_update_position_code(inventory_id, aisle_id, position_id, body, update_pos_code_uc)
        return
    if action == ReviewActionType.DELETE_POSITION:
        handle_delete_position(inventory_id, aisle_id, position_id, body.job_id, delete_uc)
        return
