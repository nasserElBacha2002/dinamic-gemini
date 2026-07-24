"""v3 authoritative aisle finalization routes (Phase 6)."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from src.api.dependencies import (
    get_aisle_repo,
    get_evaluate_authoritative_aisle_readiness,
    get_finalize_authoritative_aisle_use_case,
    get_inventory_repo,
)
from src.api.errors import reraise_if_mapped
from src.api.errors.structured_api_http import StructuredApiHttpError
from src.api.schemas.authoritative_aisle_finalization_schemas import (
    AuthoritativeAisleReadinessResponse,
    AuthoritativeExclusionRequest,
    AuthoritativeExclusionResponse,
    FinalizeAuthoritativeAisleRequest,
    FinalizeAuthoritativeAisleResponse,
)
from src.application.errors import AisleNotFoundError, InventoryNotFoundError
from src.application.ports.repositories import AisleRepository, InventoryRepository
from src.application.services.aisle_inventory_scope import require_aisle_scoped_to_inventory
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
from src.domain.authoritative_aisle_finalization.entities import (
    AuthoritativeAisleExcludedAsset,
    AuthoritativeExclusionReason,
)
from src.runtime.app_container import get_app_container

logger = logging.getLogger(__name__)
router = APIRouter()

AUTH_EXCLUSION_DISABLED = "AUTHORITATIVE_EXCLUSION_DISABLED"
AUTH_EXCLUSION_INVALID_REASON = "AUTHORITATIVE_EXCLUSION_INVALID_REASON"


@router.get(
    "/{inventory_id}/aisles/{aisle_id}/authoritative-readiness",
    response_model=AuthoritativeAisleReadinessResponse,
    summary="Evaluate authoritative local-authority aisle readiness",
)
def get_authoritative_aisle_readiness(
    inventory_id: str,
    aisle_id: str,
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    readiness: EvaluateAuthoritativeAisleReadiness = Depends(
        get_evaluate_authoritative_aisle_readiness
    ),
) -> AuthoritativeAisleReadinessResponse:
    if inventory_repo.get_by_id(inventory_id) is None:
        raise StructuredApiHttpError(
            404, error_code="INVENTORY_NOT_FOUND", detail=f"Inventory {inventory_id} not found"
        )
    try:
        require_aisle_scoped_to_inventory(
            aisle_repo, inventory_id=inventory_id, aisle_id=aisle_id
        )
    except AisleNotFoundError as exc:
        reraise_if_mapped(exc)
        raise StructuredApiHttpError(
            404, error_code="AISLE_NOT_FOUND", detail=str(exc)
        ) from exc

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
        can_apply=result.can_apply,
        can_finalize=result.can_finalize,
    )


@router.post(
    "/{inventory_id}/aisles/{aisle_id}/assets/{asset_id}/authoritative-exclusion",
    response_model=AuthoritativeExclusionResponse,
    summary="Record explicit exclusion for authoritative finalization",
)
def post_authoritative_exclusion(
    inventory_id: str,
    aisle_id: str,
    asset_id: str,
    body: AuthoritativeExclusionRequest,
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    user: AuthUser = Depends(get_current_admin),
) -> AuthoritativeExclusionResponse:
    from src.config import load_settings

    settings = load_settings()
    if not bool(getattr(settings, "server_authoritative_aisle_finalization_enabled", False)):
        raise StructuredApiHttpError(
            404,
            error_code=AUTH_EXCLUSION_DISABLED,
            detail="Authoritative exclusion is not enabled",
        )
    if inventory_repo.get_by_id(inventory_id) is None:
        raise StructuredApiHttpError(
            404, error_code="INVENTORY_NOT_FOUND", detail=f"Inventory {inventory_id} not found"
        )
    try:
        require_aisle_scoped_to_inventory(
            aisle_repo, inventory_id=inventory_id, aisle_id=aisle_id
        )
    except AisleNotFoundError as exc:
        raise StructuredApiHttpError(
            404, error_code="AISLE_NOT_FOUND", detail=str(exc)
        ) from exc

    reason = (body.reason or "").strip().upper()
    allowed = {r.value for r in AuthoritativeExclusionReason}
    if reason not in allowed:
        raise StructuredApiHttpError(
            422,
            error_code=AUTH_EXCLUSION_INVALID_REASON,
            detail=f"Invalid exclusion reason; allowed={sorted(allowed)}",
        )

    now = datetime.now(timezone.utc)
    row = AuthoritativeAisleExcludedAsset(
        id=str(uuid.uuid4()),
        inventory_id=inventory_id,
        aisle_id=aisle_id,
        asset_id=asset_id.strip(),
        reason=reason,
        excluded_by=str(getattr(user, "id", "") or ""),
        excluded_at=now,
        is_current=True,
        created_at=now,
        updated_at=now,
    )
    get_app_container().get_authoritative_aisle_finalization_repo().upsert_exclusion(row)
    return AuthoritativeExclusionResponse(
        asset_id=row.asset_id,
        reason=row.reason,
        excluded_at=row.excluded_at.isoformat(),
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
        code = (
            "INVENTORY_NOT_FOUND"
            if isinstance(exc, InventoryNotFoundError)
            else "AISLE_NOT_FOUND"
        )
        raise StructuredApiHttpError(404, error_code=code, detail=str(exc)) from exc

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
