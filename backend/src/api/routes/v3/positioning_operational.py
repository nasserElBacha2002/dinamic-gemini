"""Phase 7 positioning operational UX routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from src.api.dependencies import (
    get_access_principal,
    get_aisle_operational_positioning_view_use_case,
    get_aisle_positioning_sequence_use_case,
    get_reprocess_aisle_positioning_use_case,
)
from src.api.errors.error_mapping import reraise_if_mapped
from src.api.schemas.positioning_operational_schemas import (
    AisleOperationalPositioningViewResponse,
    PositioningReprocessRequest,
    PositioningReprocessResponse,
    PositioningSequenceResponse,
    frame_to_dto,
    view_to_response,
)
from src.application.dto.access_principal import AccessPrincipal
from src.application.errors import AisleNotFoundError, InventoryNotFoundError, JobNotFoundError
from src.application.position_override_errors import PositionOverrideAccessDeniedError
from src.application.use_cases.positioning_operational.get_aisle_operational_view import (
    GetAisleOperationalPositioningViewCommand,
    GetAisleOperationalPositioningViewUseCase,
)
from src.application.use_cases.positioning_operational.get_aisle_positioning_sequence import (
    GetAislePositioningSequenceCommand,
    GetAislePositioningSequenceUseCase,
)
from src.application.use_cases.positioning_operational.reprocess_aisle_positioning import (
    PositioningReprocessError,
    ReprocessAislePositioningCommand,
    ReprocessAislePositioningUseCase,
)

router = APIRouter()


@router.get(
    "/{inventory_id}/aisles/{aisle_id}/positioning-operational-view",
    response_model=AisleOperationalPositioningViewResponse,
)
def get_positioning_operational_view(
    inventory_id: str,
    aisle_id: str,
    job_id: str | None = Query(default=None),
    principal: AccessPrincipal = Depends(get_access_principal),
    use_case: GetAisleOperationalPositioningViewUseCase = Depends(
        get_aisle_operational_positioning_view_use_case
    ),
) -> AisleOperationalPositioningViewResponse:
    try:
        view = use_case.execute(
            GetAisleOperationalPositioningViewCommand(
                inventory_id=inventory_id,
                aisle_id=aisle_id,
                principal=principal,
                job_id=job_id,
            )
        )
        return view_to_response(view)
    except (AisleNotFoundError, InventoryNotFoundError) as e:
        reraise_if_mapped(e)
        raise


@router.get(
    "/{inventory_id}/aisles/{aisle_id}/positioning-sequence",
    response_model=PositioningSequenceResponse,
)
def get_positioning_sequence(
    inventory_id: str,
    aisle_id: str,
    job_id: str = Query(...),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    principal: AccessPrincipal = Depends(get_access_principal),
    use_case: GetAislePositioningSequenceUseCase = Depends(
        get_aisle_positioning_sequence_use_case
    ),
) -> PositioningSequenceResponse:
    try:
        result = use_case.execute(
            GetAislePositioningSequenceCommand(
                inventory_id=inventory_id,
                aisle_id=aisle_id,
                principal=principal,
                job_id=job_id,
                page=page,
                page_size=page_size,
            )
        )
        return PositioningSequenceResponse(
            job_id=result.job_id,
            items=[frame_to_dto(f) for f in result.items],
            total=result.total,
            page=result.page,
            page_size=result.page_size,
        )
    except (AisleNotFoundError, JobNotFoundError) as e:
        reraise_if_mapped(e)
        raise


@router.get(
    "/{inventory_id}/aisles/{aisle_id}/positioning-warnings",
    response_model=AisleOperationalPositioningViewResponse,
)
def get_positioning_warnings(
    inventory_id: str,
    aisle_id: str,
    job_id: str | None = Query(default=None),
    principal: AccessPrincipal = Depends(get_access_principal),
    use_case: GetAisleOperationalPositioningViewUseCase = Depends(
        get_aisle_operational_positioning_view_use_case
    ),
) -> AisleOperationalPositioningViewResponse:
    """Warnings are part of the operational view; alias for clients that only need diagnostics."""
    return get_positioning_operational_view(
        inventory_id=inventory_id,
        aisle_id=aisle_id,
        job_id=job_id,
        principal=principal,
        use_case=use_case,
    )


@router.post(
    "/{inventory_id}/aisles/{aisle_id}/reprocess",
    response_model=PositioningReprocessResponse,
)
def reprocess_aisle_positioning(
    inventory_id: str,
    aisle_id: str,
    body: PositioningReprocessRequest,
    principal: AccessPrincipal = Depends(get_access_principal),
    use_case: ReprocessAislePositioningUseCase = Depends(
        get_reprocess_aisle_positioning_use_case
    ),
):
    try:
        result = use_case.execute(
            ReprocessAislePositioningCommand(
                inventory_id=inventory_id,
                aisle_id=aisle_id,
                principal=principal,
                idempotency_key=body.idempotency_key,
                reprocess_mode=body.reprocess_mode,
                expected_active_job_id=body.expected_active_job_id,
                expected_result_job_id=body.expected_result_job_id,
                identification_mode=body.identification_mode,
            )
        )
        return PositioningReprocessResponse(
            mode=result.mode,
            job_id=result.job_id,
            reconciliation_id=result.reconciliation_id,
            detail=result.detail,
            manuals_preserved=result.manuals_preserved,
            manual_override_policy=result.manual_override_policy,
            previous_manual_overrides_count=result.previous_manual_overrides_count,
        )
    except PositioningReprocessError as exc:
        return JSONResponse(
            status_code=exc.http_status,
            content=jsonable_encoder({"code": exc.code, "detail": exc.detail}),
        )
    except PositionOverrideAccessDeniedError as exc:
        return JSONResponse(
            status_code=exc.http_status,
            content=jsonable_encoder({"code": exc.code, "detail": exc.detail}),
        )
    except (AisleNotFoundError, InventoryNotFoundError) as e:
        reraise_if_mapped(e)
        raise
