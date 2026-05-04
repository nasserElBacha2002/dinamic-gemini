"""v3 position review actions: confirm, corrections, mark_unknown, mark_image_mismatch, delete_position."""

from __future__ import annotations

from dataclasses import dataclass

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


@dataclass(frozen=True)
class _ReviewActionDependencies:
    confirm_uc: ConfirmPositionUseCase
    mark_unknown_uc: MarkPositionUnknownUseCase
    mark_image_mismatch_uc: MarkPositionImageMismatchUseCase
    update_quantity_uc: UpdateProductQuantityUseCase
    update_sku_uc: UpdateProductSkuUseCase
    update_pos_code_uc: UpdatePositionCodeUseCase
    delete_uc: DeletePositionUseCase


def get_review_action_dependencies(  # noqa: PLR0913
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
) -> _ReviewActionDependencies:
    # One Depends() per injected use case — arity follows DI wiring.
    return _ReviewActionDependencies(
        confirm_uc=confirm_uc,
        mark_unknown_uc=mark_unknown_uc,
        mark_image_mismatch_uc=mark_image_mismatch_uc,
        update_quantity_uc=update_quantity_uc,
        update_sku_uc=update_sku_uc,
        update_pos_code_uc=update_pos_code_uc,
        delete_uc=delete_uc,
    )


def _dispatch_review_action(
    inventory_id: str,
    aisle_id: str,
    position_id: str,
    body: ReviewActionRequest,
    deps: _ReviewActionDependencies,
) -> None:
    """Dispatch by action_type — keeps submit_review_action shallow (PLR)."""
    action = body.action_type
    if action == ReviewActionType.CONFIRM:
        handle_confirm(inventory_id, aisle_id, position_id, body.job_id, deps.confirm_uc)
        return
    if action == ReviewActionType.MARK_UNKNOWN:
        handle_mark_unknown(inventory_id, aisle_id, position_id, body.job_id, deps.mark_unknown_uc)
        return
    if action == ReviewActionType.MARK_IMAGE_MISMATCH:
        handle_mark_image_mismatch(
            inventory_id, aisle_id, position_id, body.job_id, deps.mark_image_mismatch_uc
        )
        return
    if action == ReviewActionType.UPDATE_QUANTITY:
        handle_update_quantity(inventory_id, aisle_id, position_id, body, deps.update_quantity_uc)
        return
    if action == ReviewActionType.UPDATE_SKU:
        handle_update_sku(inventory_id, aisle_id, position_id, body, deps.update_sku_uc)
        return
    if action == ReviewActionType.UPDATE_POSITION_CODE:
        handle_update_position_code(
            inventory_id, aisle_id, position_id, body, deps.update_pos_code_uc
        )
        return
    if action == ReviewActionType.DELETE_POSITION:
        handle_delete_position(inventory_id, aisle_id, position_id, body.job_id, deps.delete_uc)


@router.post(
    "/{inventory_id}/aisles/{aisle_id}/positions/{position_id}/reviews",
    status_code=204,
)
def submit_review_action(
    inventory_id: str,
    aisle_id: str,
    position_id: str,
    body: ReviewActionRequest,
    deps: _ReviewActionDependencies = Depends(get_review_action_dependencies),
) -> None:
    """Submit a manual review action (confirm, corrections, mark_unknown, mark_image_mismatch, delete_position)."""
    # Pydantic validates ``action_type`` as ``ReviewActionType`` (same wire strings as the domain enum).
    _dispatch_review_action(inventory_id, aisle_id, position_id, body, deps)
