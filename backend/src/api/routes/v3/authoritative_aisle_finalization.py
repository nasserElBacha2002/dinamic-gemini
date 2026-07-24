"""v3 authoritative aisle finalization routes (Phase 6)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from src.api.dependencies import (
    get_evaluate_authoritative_aisle_readiness,
    get_finalize_authoritative_aisle_use_case,
)
from src.api.errors import reraise_if_mapped
from src.api.errors.structured_api_http import StructuredApiHttpError
from src.api.schemas.authoritative_aisle_finalization_schemas import (
    AuthoritativeAisleReadinessResponse,
    FinalizeAuthoritativeAisleRequest,
    FinalizeAuthoritativeAisleResponse,
)
from src.application.errors import AisleNotFoundError, InventoryNotFoundError
from src.application.services.evaluate_authoritative_aisle_readiness import (
    EvaluateAuthoritativeAisleReadiness,
)
from src.application.use_cases.aisles.finalize_authoritative_aisle import (
    AUTH_FINALIZATION_CONFLICT,
    AUTH_FINALIZATION_COUNT_MISMATCH,
    AUTH_FINALIZATION_DISABLED,
    AUTH_FINALIZATION_LOCK,
    AUTH_FINALIZATION_NOT_READY,
    AuthoritativeFinalizationConflictError,
    AuthoritativeFinalizationDisabledError,
    AuthoritativeFinalizationLockError,
    AuthoritativeFinalizationNotReadyError,
    FinalizeAuthoritativeAisle,
    FinalizeAuthoritativeAisleCommand,
)
from src.auth.dependencies import get_current_admin
from src.auth.schemas import AuthUser

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get(
    "/{inventory_id}/aisles/{aisle_id}/authoritative-readiness",
    response_model=AuthoritativeAisleReadinessResponse,
    summary="Evaluate authoritative local-authority aisle readiness",
)
def get_authoritative_aisle_readiness(
    inventory_id: str,
    aisle_id: str,
    readiness: EvaluateAuthoritativeAisleReadiness = Depends(
        get_evaluate_authoritative_aisle_readiness
    ),
) -> AuthoritativeAisleReadinessResponse:
    result = readiness.execute(inventory_id=inventory_id, aisle_id=aisle_id)
    return AuthoritativeAisleReadinessResponse(
        status=result.status.value,
        total_images=result.total_images,
        applied_images=result.applied_images,
        excluded_images=result.excluded_images,
        pending_images=result.pending_images,
        conflicted_images=result.conflicted_images,
        failed_images=result.failed_images,
        reasons=list(result.reasons),
        unique_codes=result.unique_codes,
        total_quantity=result.total_quantity,
    )


@router.post(
    "/{inventory_id}/aisles/{aisle_id}/finalize-authoritative",
    response_model=FinalizeAuthoritativeAisleResponse,
    summary="Finalize aisle from local authoritative CODE_SCAN results",
)
def post_finalize_authoritative_aisle(
    inventory_id: str,
    aisle_id: str,
    body: FinalizeAuthoritativeAisleRequest,
    use_case: FinalizeAuthoritativeAisle = Depends(get_finalize_authoritative_aisle_use_case),
    user: AuthUser = Depends(get_current_admin),
) -> FinalizeAuthoritativeAisleResponse:
    try:
        result = use_case.execute(
            FinalizeAuthoritativeAisleCommand(
                inventory_id=inventory_id,
                aisle_id=aisle_id,
                finalization_id=body.finalization_id.strip(),
                expected_asset_count=body.expected_asset_count,
                client_session_id=(body.client_session_id or None),
                confirmed_by_user_id=str(getattr(user, "id", "") or ""),
            )
        )
    except AuthoritativeFinalizationDisabledError as exc:
        raise StructuredApiHttpError(
            404,
            error_code=AUTH_FINALIZATION_DISABLED,
            detail=str(exc),
        ) from exc
    except AuthoritativeFinalizationNotReadyError as exc:
        raise StructuredApiHttpError(
            409,
            error_code=AUTH_FINALIZATION_NOT_READY,
            detail=";".join(exc.reasons) or str(exc),
        ) from exc
    except AuthoritativeFinalizationLockError as exc:
        raise StructuredApiHttpError(
            409,
            error_code=AUTH_FINALIZATION_LOCK,
            detail=str(exc),
        ) from exc
    except AuthoritativeFinalizationConflictError as exc:
        status = 409
        code = exc.error_code
        if code == AUTH_FINALIZATION_COUNT_MISMATCH:
            status = 422
        raise StructuredApiHttpError(status, error_code=code, detail=str(exc)) from exc
    except (AisleNotFoundError, InventoryNotFoundError) as exc:
        reraise_if_mapped(exc)
        raise StructuredApiHttpError(
            404,
            error_code="AISLE_NOT_FOUND",
            detail=str(exc),
        ) from exc

    logger.info(
        "authoritative_aisle_finalization_api finalization_id=%s aisle_id=%s replay=%s",
        result.finalization_id,
        aisle_id,
        result.idempotent_replay,
    )
    return FinalizeAuthoritativeAisleResponse(
        finalization_id=result.finalization_id,
        status=result.status,
        aisle_status=result.aisle_status,
        total_assets=result.total_assets,
        applied_assets=result.applied_assets,
        excluded_assets=result.excluded_assets,
        position_count=result.position_count,
        idempotent_replay=result.idempotent_replay,
    )
