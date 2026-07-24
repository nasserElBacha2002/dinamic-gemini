"""v3 server reprocess routes (Phase 7) — proposals; no automatic overwrite."""

from __future__ import annotations

import logging
from datetime import timezone

from fastapi import APIRouter, Depends, Query

from src.api.errors import reraise_if_mapped
from src.api.errors.structured_api_http import StructuredApiHttpError
from src.api.schemas.server_reprocess_schemas import (
    ServerReprocessAdoptRequest,
    ServerReprocessAdoptResponse,
    ServerReprocessCompleteWithResultsRequest,
    ServerReprocessDetailResponse,
    ServerReprocessProposalItemResponse,
    ServerReprocessProposalSummaryResponse,
    ServerReprocessRequest,
    ServerReprocessRunResponse,
)
from src.application.errors import AisleNotFoundError, InventoryNotFoundError
from src.application.use_cases.aisles.adopt_server_reprocess_proposals import (
    AdoptItemCommand,
    AdoptServerReprocessCommand,
    AdoptServerReprocessProposals,
    ServerReprocessAdoptionConflictError,
    ServerReprocessAdoptionDisabledError,
    ServerReprocessStaleProposalError,
)
from src.application.use_cases.aisles.build_server_reprocess_proposals import (
    ServerReprocessInvalidStateError,
    ServerReprocessRunNotFoundError,
)
from src.application.use_cases.aisles.create_server_reprocess_run import (
    CreateServerReprocessCommand,
    CreateServerReprocessRun,
    ServerReprocessDisabledError,
    ServerReprocessInvalidScopeError,
    ServerReprocessLockError,
    ServerReprocessRequestConflictError,
    ServerReprocessUnsupportedModeError,
)
from src.application.use_cases.aisles.execute_server_reprocess_run import (
    CancelServerReprocessRun,
    ExecuteServerReprocessRun,
)
from src.application.use_cases.aisles.list_server_reprocess_proposals import (
    ListServerReprocessProposals,
)
from src.auth.dependencies import get_current_admin
from src.auth.schemas import AuthUser
from src.domain.server_reprocess.entities import RemoteProposalInput
from src.runtime.app_container import get_app_container

logger = logging.getLogger(__name__)
router = APIRouter()


def _iso(dt) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _run_response(
    run,
    *,
    replayed: bool = False,
    initial_server_processing: bool = False,
) -> ServerReprocessRunResponse:
    return ServerReprocessRunResponse(
        id=run.id,
        request_id=run.request_id,
        inventory_id=run.inventory_id,
        aisle_id=run.aisle_id,
        run_type=run.run_type,
        scope_type=run.scope_type,
        processing_mode=run.processing_mode,
        reason=run.reason,
        status=run.status,
        review_status=run.review_status,
        has_prior_authority=bool(run.has_prior_authority),
        requested_by=run.requested_by,
        requested_at=_iso(run.requested_at) or "",
        started_at=_iso(run.started_at),
        completed_at=_iso(run.completed_at),
        canceled_at=_iso(run.canceled_at),
        failure_code=run.failure_code,
        failure_message=run.failure_message,
        row_version=run.row_version,
        replayed=replayed,
        initial_server_processing=initial_server_processing,
        has_pending_server_reprocess=run.status
        in ("REQUESTED", "QUEUED", "RUNNING", "COMPLETED")
        and run.review_status in ("NOT_REVIEWED", "REVIEW_IN_PROGRESS"),
    )


def _get_create() -> CreateServerReprocessRun:
    container = get_app_container()
    uc = getattr(container, "create_server_reprocess_run", None)
    if uc is None:
        raise StructuredApiHttpError(
            503,
            error_code="SERVER_REPROCESS_UNAVAILABLE",
            detail="Server reprocess is not configured",
        )
    return uc


def _get_list() -> ListServerReprocessProposals:
    return get_app_container().list_server_reprocess_proposals


def _get_execute() -> ExecuteServerReprocessRun:
    return get_app_container().execute_server_reprocess_run


def _get_cancel() -> CancelServerReprocessRun:
    return get_app_container().cancel_server_reprocess_run


def _get_adopt() -> AdoptServerReprocessProposals:
    return get_app_container().adopt_server_reprocess_proposals


@router.post(
    "/{inventory_id}/aisles/{aisle_id}/server-reprocess",
    response_model=ServerReprocessRunResponse,
    summary="Request optional server reprocess (creates proposal run; no overwrite)",
)
def post_server_reprocess(
    inventory_id: str,
    aisle_id: str,
    body: ServerReprocessRequest,
    user: AuthUser = Depends(get_current_admin),
) -> ServerReprocessRunResponse:
    try:
        result = _get_create().execute(
            CreateServerReprocessCommand(
                inventory_id=inventory_id,
                aisle_id=aisle_id,
                request_id=body.request_id,
                scope_type=body.scope.type,
                asset_ids=tuple(body.scope.asset_ids or ()),
                processing_mode=body.processing_mode,
                reason=body.reason,
                requested_by=str(getattr(user, "id", None) or getattr(user, "sub", "") or "admin"),
                source_session_id=body.source_session_id,
            )
        )
    except ServerReprocessDisabledError as exc:
        raise StructuredApiHttpError(403, error_code=exc.error_code, detail=str(exc)) from exc
    except ServerReprocessUnsupportedModeError as exc:
        raise StructuredApiHttpError(422, error_code=exc.error_code, detail=str(exc)) from exc
    except ServerReprocessInvalidScopeError as exc:
        raise StructuredApiHttpError(422, error_code=exc.error_code, detail=str(exc)) from exc
    except ServerReprocessRequestConflictError as exc:
        raise StructuredApiHttpError(409, error_code=exc.error_code, detail=str(exc)) from exc
    except ServerReprocessLockError as exc:
        raise StructuredApiHttpError(409, error_code=exc.error_code, detail=str(exc)) from exc
    except InventoryNotFoundError as exc:
        reraise_if_mapped(exc)
        raise StructuredApiHttpError(
            404, error_code="INVENTORY_NOT_FOUND", detail=str(exc)
        ) from exc
    except AisleNotFoundError as exc:
        reraise_if_mapped(exc)
        raise StructuredApiHttpError(404, error_code="AISLE_NOT_FOUND", detail=str(exc)) from exc

    return _run_response(
        result.run,
        replayed=result.replayed,
        initial_server_processing=result.initial_server_processing,
    )


@router.get(
    "/{inventory_id}/aisles/{aisle_id}/server-reprocess/{run_id}",
    response_model=ServerReprocessDetailResponse,
    summary="Get server reprocess run proposals (informational comparison only)",
)
def get_server_reprocess(
    inventory_id: str,
    aisle_id: str,
    run_id: str,
    difference_type: str | None = None,
    asset_id: str | None = None,
    review_status: str | None = None,
    has_change: bool | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
) -> ServerReprocessDetailResponse:
    try:
        result = _get_list().execute(
            run_id=run_id,
            difference_type=difference_type,
            asset_id=asset_id,
            review_status=review_status,
            has_change=has_change,
            offset=offset,
            limit=limit,
        )
    except ServerReprocessRunNotFoundError as exc:
        raise StructuredApiHttpError(404, error_code=exc.error_code, detail=str(exc)) from exc

    if result.run.inventory_id != inventory_id or result.run.aisle_id != aisle_id:
        raise StructuredApiHttpError(
            404, error_code="SERVER_REPROCESS_RUN_NOT_FOUND", detail="Run not in aisle"
        )

    return ServerReprocessDetailResponse(
        run=_run_response(result.run),
        summary=ServerReprocessProposalSummaryResponse(
            total=result.summary.total,
            same=result.summary.same,
            changed=result.summary.changed,
            newly_resolved=result.summary.newly_resolved,
            unresolved=result.summary.unresolved,
            not_comparable=result.summary.not_comparable,
        ),
        items=[
            ServerReprocessProposalItemResponse(
                id=p.id,
                run_id=p.run_id,
                asset_id=p.asset_id,
                remote_result_id=p.remote_result_id,
                previous_result_id=p.previous_result_id,
                previous_position_id=p.previous_position_id,
                status=p.status,
                difference_type=p.difference_type,
                internal_code=p.internal_code,
                quantity=p.quantity,
                confidence=p.confidence,
                source=p.source,
                remote_resolved=p.remote_resolved,
                review_status=p.review_status,
            )
            for p in result.items
        ],
        snapshot=dict(result.run.snapshot_json or {}),
    )


@router.post(
    "/{inventory_id}/aisles/{aisle_id}/server-reprocess/{run_id}/complete-with-results",
    response_model=ServerReprocessDetailResponse,
    summary="Attach remote outputs as proposals (no position overwrite)",
)
def post_complete_with_results(
    inventory_id: str,
    aisle_id: str,
    run_id: str,
    body: ServerReprocessCompleteWithResultsRequest,
    user: AuthUser = Depends(get_current_admin),
) -> ServerReprocessDetailResponse:
    _ = user
    try:
        run, _proposals = _get_execute().complete_with_remote_results(
            run_id=run_id,
            remote_results=[
                RemoteProposalInput(
                    asset_id=r.asset_id,
                    remote_result_id=r.remote_result_id,
                    internal_code=r.internal_code,
                    quantity=r.quantity,
                    confidence=r.confidence,
                    source=r.source,
                    resolved=r.resolved,
                    ambiguous=r.ambiguous,
                    comparable=r.comparable,
                    global_batch_unmapped=r.global_batch_unmapped,
                )
                for r in body.results
            ],
        )
    except ServerReprocessRunNotFoundError as exc:
        raise StructuredApiHttpError(404, error_code=exc.error_code, detail=str(exc)) from exc
    except ServerReprocessInvalidStateError as exc:
        raise StructuredApiHttpError(409, error_code=exc.error_code, detail=str(exc)) from exc

    if run.inventory_id != inventory_id or run.aisle_id != aisle_id:
        raise StructuredApiHttpError(
            404, error_code="SERVER_REPROCESS_RUN_NOT_FOUND", detail="Run not in aisle"
        )
    return get_server_reprocess(inventory_id, aisle_id, run_id)


@router.post(
    "/{inventory_id}/aisles/{aisle_id}/server-reprocess/{run_id}/cancel",
    response_model=ServerReprocessRunResponse,
    summary="Cancel a server reprocess run (does not change current authority)",
)
def post_cancel_server_reprocess(
    inventory_id: str,
    aisle_id: str,
    run_id: str,
    user: AuthUser = Depends(get_current_admin),
) -> ServerReprocessRunResponse:
    _ = user
    try:
        run = _get_cancel().execute(run_id=run_id)
    except ServerReprocessRunNotFoundError as exc:
        raise StructuredApiHttpError(404, error_code=exc.error_code, detail=str(exc)) from exc
    except ServerReprocessInvalidStateError as exc:
        raise StructuredApiHttpError(409, error_code=exc.error_code, detail=str(exc)) from exc
    if run.inventory_id != inventory_id or run.aisle_id != aisle_id:
        raise StructuredApiHttpError(
            404, error_code="SERVER_REPROCESS_RUN_NOT_FOUND", detail="Run not in aisle"
        )
    return _run_response(run)


@router.post(
    "/{inventory_id}/aisles/{aisle_id}/server-reprocess/{run_id}/adopt",
    response_model=ServerReprocessAdoptResponse,
    summary="Adopt selected proposals (explicit; all-or-nothing; stale-safe)",
)
def post_adopt_server_reprocess(
    inventory_id: str,
    aisle_id: str,
    run_id: str,
    body: ServerReprocessAdoptRequest,
    user: AuthUser = Depends(get_current_admin),
) -> ServerReprocessAdoptResponse:
    try:
        result = _get_adopt().execute(
            AdoptServerReprocessCommand(
                inventory_id=inventory_id,
                aisle_id=aisle_id,
                run_id=run_id,
                adoption_id=body.adoption_id,
                adopted_by=str(
                    getattr(user, "id", None) or getattr(user, "sub", "") or "admin"
                ),
                items=tuple(
                    AdoptItemCommand(
                        proposal_id=i.proposal_id,
                        action=i.action,
                        edit_internal_code=i.edit_internal_code,
                        edit_quantity=i.edit_quantity,
                    )
                    for i in body.items
                ),
            )
        )
    except ServerReprocessAdoptionDisabledError as exc:
        raise StructuredApiHttpError(403, error_code=exc.error_code, detail=str(exc)) from exc
    except ServerReprocessStaleProposalError as exc:
        raise StructuredApiHttpError(409, error_code=exc.error_code, detail=str(exc)) from exc
    except ServerReprocessAdoptionConflictError as exc:
        raise StructuredApiHttpError(409, error_code=exc.error_code, detail=str(exc)) from exc
    except ServerReprocessLockError as exc:
        raise StructuredApiHttpError(409, error_code=exc.error_code, detail=str(exc)) from exc
    except ServerReprocessRunNotFoundError as exc:
        raise StructuredApiHttpError(404, error_code=exc.error_code, detail=str(exc)) from exc

    return ServerReprocessAdoptResponse(
        adoption_id=result.adoption.adoption_id,
        run_id=result.run.id,
        status=result.adoption.status,
        review_status=result.run.review_status,
        item_count=result.adoption.item_count,
        adopted_count=result.adoption.adopted_count,
        kept_count=result.adoption.kept_count,
        deferred_count=result.adoption.deferred_count,
        replayed=result.replayed,
    )
