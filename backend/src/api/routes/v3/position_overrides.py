"""Phase 6 manual product-position override endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from src.api.dependencies import (
    get_access_principal,
    get_list_position_override_history_use_case,
    get_manage_position_override_use_case,
)
from src.api.schemas.position_override_schemas import (
    PositionHistoryResponse,
    PositionOverrideMutationResponse,
    PositionOverrideRequest,
    RestoreAutomaticRequest,
    automatic_to_history_response,
    effective_to_response,
    override_to_response,
)
from src.application.dto.access_principal import AccessPrincipal
from src.application.position_override_errors import (
    PositionOverrideError,
    PositionOverrideInvalidActionError,
)
from src.application.use_cases.position_overrides.manage import (
    ListPositionOverrideHistoryUseCase,
    ManagePositionOverrideUseCase,
    PositionOverrideCommand,
)
from src.domain.position_overrides.entities import PositionOverrideAction

router = APIRouter()


def _error_response(exc: PositionOverrideError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.http_status,
        content=jsonable_encoder(
            {"code": exc.code, "detail": exc.detail, **exc.metadata}
        ),
    )


@router.post(
    "/{inventory_id}/jobs/{job_id}/results/{result_id}/position-override",
    response_model=PositionOverrideMutationResponse,
)
def create_position_override(
    inventory_id: str,
    job_id: str,
    result_id: str,
    body: PositionOverrideRequest,
    principal: AccessPrincipal = Depends(get_access_principal),
    use_case: ManagePositionOverrideUseCase = Depends(
        get_manage_position_override_use_case
    ),
):
    try:
        if body.action is PositionOverrideAction.RESTORE_AUTOMATIC:
            raise PositionOverrideInvalidActionError(
                "Use the restore endpoint for RESTORE_AUTOMATIC."
            )
        result = use_case.execute(
            PositionOverrideCommand(
                inventory_id=inventory_id,
                job_id=job_id,
                result_id=result_id,
                action=body.action,
                position_label_id=body.position_label_id,
                reason_code=body.reason_code,
                reason_text=body.reason_text,
                expected_effective_version=body.expected_version,
                idempotency_key=body.idempotency_key,
                principal=principal,
            )
        )
    except PositionOverrideError as exc:
        return _error_response(exc)
    return PositionOverrideMutationResponse(
        revision=override_to_response(result.revision),
        current_effective=effective_to_response(result.current_effective),
    )


@router.post(
    "/{inventory_id}/jobs/{job_id}/results/{result_id}/position-override/restore",
    response_model=PositionOverrideMutationResponse,
)
def restore_automatic_position(
    inventory_id: str,
    job_id: str,
    result_id: str,
    body: RestoreAutomaticRequest,
    principal: AccessPrincipal = Depends(get_access_principal),
    use_case: ManagePositionOverrideUseCase = Depends(
        get_manage_position_override_use_case
    ),
):
    try:
        result = use_case.execute(
            PositionOverrideCommand(
                inventory_id=inventory_id,
                job_id=job_id,
                result_id=result_id,
                action=PositionOverrideAction.RESTORE_AUTOMATIC,
                position_label_id=None,
                reason_code=body.reason_code,
                reason_text=body.reason_text,
                expected_effective_version=body.expected_version,
                idempotency_key=body.idempotency_key,
                principal=principal,
            )
        )
    except PositionOverrideError as exc:
        return _error_response(exc)
    return PositionOverrideMutationResponse(
        revision=override_to_response(result.revision),
        current_effective=effective_to_response(result.current_effective),
    )


@router.get(
    "/{inventory_id}/jobs/{job_id}/results/{result_id}/position-history",
    response_model=PositionHistoryResponse,
)
def get_position_history(
    inventory_id: str,
    job_id: str,
    result_id: str,
    principal: AccessPrincipal = Depends(get_access_principal),
    use_case: ListPositionOverrideHistoryUseCase = Depends(
        get_list_position_override_history_use_case
    ),
):
    try:
        effective, automatic_rows, manual_rows = use_case.execute(
            inventory_id=inventory_id,
            job_id=job_id,
            result_id=result_id,
            principal=principal,
        )
    except PositionOverrideError as exc:
        return _error_response(exc)
    return PositionHistoryResponse(
        effective=effective_to_response(effective),
        automatic_revisions=[
            automatic_to_history_response(row) for row in automatic_rows
        ],
        manual_revisions=[override_to_response(row) for row in manual_rows],
    )
