"""v3 aisle revision routes (Phase 8)."""

from __future__ import annotations

from datetime import timezone

from fastapi import APIRouter, Depends, Query

from src.api.errors import reraise_if_mapped
from src.api.errors.structured_api_http import StructuredApiHttpError
from src.api.schemas.aisle_revision_schemas import (
    AisleHistoryEntryResponse,
    AisleRevisionCapabilitiesResponse,
    AisleRevisionDiffEntryResponse,
    AisleRevisionDiffResponse,
    AisleRevisionItemResponse,
    AisleRevisionResponse,
    ApplyAisleRevisionRequest,
    CreateAisleRevisionRequest,
    RollbackAisleRequest,
    UpdateAisleRevisionItemRequest,
)
from src.application.use_cases.aisles.apply_aisle_revision import (
    AisleRevisionApplyConflictError,
    AisleRevisionStaleError,
    ApplyAisleRevisionCommand,
    CreateRollbackCommand,
)
from src.application.use_cases.aisles.manage_aisle_revisions import (
    AisleNotFinalizedError,
    AisleRevisionConflictError,
    AisleRevisionDisabledError,
    AisleRevisionLockError,
    AisleRevisionNotEditableError,
    AisleRevisionNotFoundError,
    CreateAisleRevisionCommand,
    UpdateAisleRevisionItemCommand,
)
from src.auth.dependencies import get_current_admin
from src.auth.schemas import AuthUser
from src.config import load_settings
from src.runtime.app_container import get_app_container

router = APIRouter()


def _require_actor_id(user: AuthUser) -> str:
    actor = (getattr(user, "id", None) or "").strip()
    if not actor:
        raise StructuredApiHttpError(
            401,
            error_code="AISLE_REVISION_ACTOR_REQUIRED",
            detail="Authenticated user id is required",
        )
    return actor


def _iso(dt) -> str | None:
    if dt is None:
        return None
    if getattr(dt, "tzinfo", None) is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _item_response(item) -> AisleRevisionItemResponse:
    return AisleRevisionItemResponse(
        id=item.id,
        asset_id=item.asset_id,
        base_result_id=item.base_result_id,
        base_position_id=item.base_position_id,
        proposed_internal_code=item.proposed_internal_code,
        proposed_quantity=item.proposed_quantity,
        proposed_exclusion_state=item.proposed_exclusion_state,
        proposal_source=item.proposal_source,
        proposal_reference_id=item.proposal_reference_id,
        change_reason=item.change_reason,
        item_status=item.item_status,
    )


def _revision_response(revision, *, replayed: bool = False, include_items: bool = True):
    items = []
    if include_items:
        repo = get_app_container().get_aisle_revision_repo()
        items = [_item_response(i) for i in repo.list_items(revision.id)]
    return AisleRevisionResponse(
        id=revision.id,
        inventory_id=revision.inventory_id,
        aisle_id=revision.aisle_id,
        base_finalization_id=revision.base_finalization_id,
        new_finalization_id=revision.new_finalization_id,
        revision_type=revision.revision_type,
        status=revision.status,
        reason=revision.reason,
        requested_by=revision.requested_by,
        requested_at=_iso(revision.requested_at) or "",
        completed_at=_iso(revision.completed_at),
        apply_id=revision.apply_id,
        content_hash=revision.content_hash,
        row_version=revision.row_version,
        replayed=replayed,
        items=items,
    )


def _map_errors(exc: Exception) -> None:
    if isinstance(exc, AisleRevisionDisabledError):
        raise StructuredApiHttpError(
            404, error_code=exc.error_code, detail=str(exc)
        ) from exc
    if isinstance(exc, AisleRevisionNotFoundError):
        raise StructuredApiHttpError(
            404, error_code=exc.error_code, detail=str(exc)
        ) from exc
    if isinstance(exc, AisleNotFinalizedError):
        raise StructuredApiHttpError(
            409, error_code=exc.error_code, detail=str(exc)
        ) from exc
    if isinstance(exc, AisleRevisionStaleError):
        raise StructuredApiHttpError(
            409, error_code=exc.error_code, detail=str(exc)
        ) from exc
    if isinstance(
        exc,
        (
            AisleRevisionConflictError,
            AisleRevisionApplyConflictError,
            AisleRevisionNotEditableError,
            AisleRevisionLockError,
        ),
    ):
        code = getattr(exc, "error_code", "AISLE_REVISION_CONFLICT")
        raise StructuredApiHttpError(409, error_code=code, detail=str(exc)) from exc
    reraise_if_mapped(exc)
    raise


@router.get(
    "/{inventory_id}/aisles/{aisle_id}/revision-capabilities",
    response_model=AisleRevisionCapabilitiesResponse,
)
def get_revision_capabilities(
    inventory_id: str,
    aisle_id: str,
    _user: AuthUser = Depends(get_current_admin),
) -> AisleRevisionCapabilitiesResponse:
    container = get_app_container()
    from src.application.use_cases.aisles.get_aisle_revision_capabilities import (
        GetAisleRevisionCapabilities,
    )
    from src.config import load_settings

    settings = load_settings()
    try:
        caps = GetAisleRevisionCapabilities(
            revisions_enabled=bool(
                getattr(settings, "server_aisle_revisions_enabled", False)
            ),
            rollback_enabled=bool(
                getattr(settings, "server_aisle_rollback_enabled", False)
            ),
            inventory_repo=container.get_inventory_repo(),
            aisle_repo=container.get_aisle_repo(),
            finalization_repo=container.get_authoritative_aisle_finalization_repo(),
            revision_repo=container.get_aisle_revision_repo(),
        ).execute(inventory_id=inventory_id, aisle_id=aisle_id)
    except Exception as exc:
        _map_errors(exc)
        raise
    return AisleRevisionCapabilitiesResponse(
        aisle_revisions_enabled=caps.aisle_revisions_enabled,
        aisle_rollback_enabled=caps.aisle_rollback_enabled,
        aisle_history_enabled=caps.aisle_history_enabled,
    )


@router.post(
    "/{inventory_id}/aisles/{aisle_id}/revisions",
    response_model=AisleRevisionResponse,
    status_code=201,
)
def create_revision(
    inventory_id: str,
    aisle_id: str,
    body: CreateAisleRevisionRequest,
    user: AuthUser = Depends(get_current_admin),
) -> AisleRevisionResponse:
    try:
        revision, replayed = get_app_container().create_aisle_revision.execute(
            CreateAisleRevisionCommand(
                inventory_id=inventory_id,
                aisle_id=aisle_id,
                revision_id=body.revision_id,
                revision_type=body.revision_type,
                reason=body.reason,
                requested_by=_require_actor_id(user),
            )
        )
        return _revision_response(revision, replayed=replayed)
    except Exception as exc:
        _map_errors(exc)
        raise


@router.put(
    "/{inventory_id}/aisles/{aisle_id}/revisions/{revision_id}/items/{asset_id}",
    response_model=AisleRevisionItemResponse,
)
def update_revision_item(
    inventory_id: str,
    aisle_id: str,
    revision_id: str,
    asset_id: str,
    body: UpdateAisleRevisionItemRequest,
    user: AuthUser = Depends(get_current_admin),
) -> AisleRevisionItemResponse:
    try:
        item = get_app_container().update_aisle_revision_item.execute(
            UpdateAisleRevisionItemCommand(
                inventory_id=inventory_id,
                aisle_id=aisle_id,
                revision_id=revision_id,
                asset_id=asset_id,
                actor_id=_require_actor_id(user),
                internal_code=body.internal_code,
                quantity=body.quantity,
                exclusion_action=body.exclusion_action,
                reason=body.reason,
                proposal_source=body.proposal_source,
                proposal_reference_id=body.proposal_reference_id,
            )
        )
        return _item_response(item)
    except Exception as exc:
        _map_errors(exc)
        raise


@router.post(
    "/{inventory_id}/aisles/{aisle_id}/revisions/{revision_id}/apply",
    response_model=AisleRevisionResponse,
)
def apply_revision(
    inventory_id: str,
    aisle_id: str,
    revision_id: str,
    body: ApplyAisleRevisionRequest,
    user: AuthUser = Depends(get_current_admin),
) -> AisleRevisionResponse:
    try:
        revision = get_app_container().apply_aisle_revision.execute(
            ApplyAisleRevisionCommand(
                inventory_id=inventory_id,
                aisle_id=aisle_id,
                revision_id=revision_id,
                apply_id=body.apply_id,
                expected_base_finalization_id=body.expected_base_finalization_id,
                applied_by=_require_actor_id(user),
            )
        )
        return _revision_response(revision)
    except Exception as exc:
        _map_errors(exc)
        raise


@router.get(
    "/{inventory_id}/aisles/{aisle_id}/revisions/{revision_id}/diff",
    response_model=AisleRevisionDiffResponse,
)
def get_revision_diff(
    inventory_id: str,
    aisle_id: str,
    revision_id: str,
    _user: AuthUser = Depends(get_current_admin),
) -> AisleRevisionDiffResponse:
    try:
        revision, entries = get_app_container().get_aisle_revision_diff.execute(
            inventory_id=inventory_id, aisle_id=aisle_id, revision_id=revision_id
        )
        return AisleRevisionDiffResponse(
            revision_id=revision.id,
            entries=[
                AisleRevisionDiffEntryResponse(
                    asset_id=e.asset_id,
                    kind=e.kind,
                    base_internal_code=e.base_internal_code,
                    proposed_internal_code=e.proposed_internal_code,
                    base_quantity=e.base_quantity,
                    proposed_quantity=e.proposed_quantity,
                    item_status=e.item_status,
                    proposal_source=e.proposal_source,
                )
                for e in entries
            ],
        )
    except Exception as exc:
        _map_errors(exc)
        raise


@router.get(
    "/{inventory_id}/aisles/{aisle_id}/revision-history",
    response_model=list[AisleHistoryEntryResponse],
)
def list_revision_history(
    inventory_id: str,
    aisle_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    _user: AuthUser = Depends(get_current_admin),
) -> list[AisleHistoryEntryResponse]:
    try:
        rows = get_app_container().list_aisle_history.execute(
            inventory_id=inventory_id, aisle_id=aisle_id, limit=limit
        )
        return [
            AisleHistoryEntryResponse(
                revision_id=r["revision_id"],
                revision_type=r["revision_type"],
                status=r["status"],
                reason=r["reason"],
                requested_by=r["requested_by"],
                requested_at=_iso(r["requested_at"]) or "",
                completed_at=_iso(r.get("completed_at")),
                base_finalization_id=r["base_finalization_id"],
                new_finalization_id=r.get("new_finalization_id"),
                changed_asset_count=int(r["changed_asset_count"]),
                total_assets=int(r["total_assets"]),
            )
            for r in rows
        ]
    except Exception as exc:
        _map_errors(exc)
        raise


@router.post(
    "/{inventory_id}/aisles/{aisle_id}/revisions/{revision_id}/cancel",
    response_model=AisleRevisionResponse,
)
def cancel_revision(
    inventory_id: str,
    aisle_id: str,
    revision_id: str,
    _user: AuthUser = Depends(get_current_admin),
) -> AisleRevisionResponse:
    try:
        revision = get_app_container().cancel_aisle_revision.execute(
            inventory_id=inventory_id, aisle_id=aisle_id, revision_id=revision_id
        )
        return _revision_response(revision, include_items=False)
    except Exception as exc:
        _map_errors(exc)
        raise


@router.post(
    "/{inventory_id}/aisles/{aisle_id}/rollback",
    response_model=AisleRevisionResponse,
)
def rollback_aisle(
    inventory_id: str,
    aisle_id: str,
    body: RollbackAisleRequest,
    user: AuthUser = Depends(get_current_admin),
) -> AisleRevisionResponse:
    settings = load_settings()
    if not bool(getattr(settings, "server_aisle_rollback_enabled", False)):
        raise StructuredApiHttpError(
            404,
            error_code="AISLE_ROLLBACK_DISABLED",
            detail="Aisle rollback is disabled",
        )
    try:
        revision = get_app_container().create_rollback_revision.execute(
            CreateRollbackCommand(
                inventory_id=inventory_id,
                aisle_id=aisle_id,
                rollback_id=body.rollback_id,
                target_finalization_id=body.target_finalization_id,
                reason=body.reason,
                requested_by=_require_actor_id(user),
                apply_immediately=body.apply_immediately,
            )
        )
        return _revision_response(revision)
    except Exception as exc:
        _map_errors(exc)
        raise
