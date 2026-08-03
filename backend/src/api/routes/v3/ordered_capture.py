"""v3 ordered capture sessions — Phase 1 positioning foundation (create / get / seal)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from src.api.dependencies import (
    get_access_principal,
    get_create_ordered_capture_session_use_case,
    get_get_ordered_capture_session_use_case,
    get_seal_ordered_capture_session_use_case,
    require_inventory_client_scope,
)
from src.api.errors import reraise_if_mapped
from src.api.schemas.ordered_capture_schemas import (
    OrderedCaptureSessionResponse,
    SealOrderedCaptureSessionRequest,
    ordered_capture_session_to_response,
)
from src.application.dto.access_principal import AccessPrincipal
from src.application.errors import StrategyDisabledError
from src.application.use_cases.ordered_capture.manage_ordered_capture_session import (
    CreateOrderedCaptureSessionCommand,
    CreateOrderedCaptureSessionUseCase,
    GetOrderedCaptureSessionUseCase,
    SealOrderedCaptureSessionCommand,
    SealOrderedCaptureSessionUseCase,
)
from src.config import load_settings

router = APIRouter()


def _require_ordered_capture_enabled() -> None:
    if not load_settings().ordered_capture_sessions_enabled:
        raise StrategyDisabledError("ORDERED_CAPTURE_SESSIONS_ENABLED=false")


@router.post(
    "/{inventory_id}/aisles/{aisle_id}/ordered-capture-sessions",
    response_model=OrderedCaptureSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_ordered_capture_session(
    inventory_id: str,
    aisle_id: str,
    principal: AccessPrincipal = Depends(require_inventory_client_scope),
    use_case: CreateOrderedCaptureSessionUseCase = Depends(
        get_create_ordered_capture_session_use_case
    ),
) -> OrderedCaptureSessionResponse:
    try:
        _require_ordered_capture_enabled()
        session = use_case.execute(
            CreateOrderedCaptureSessionCommand(
                inventory_id=inventory_id,
                aisle_id=aisle_id,
                principal=principal,
            )
        )
    except Exception as e:
        reraise_if_mapped(e)
        raise
    return ordered_capture_session_to_response(session)


@router.get(
    "/ordered-capture-sessions/{session_id}",
    response_model=OrderedCaptureSessionResponse,
)
def get_ordered_capture_session(
    session_id: str,
    principal: AccessPrincipal = Depends(get_access_principal),
    use_case: GetOrderedCaptureSessionUseCase = Depends(
        get_get_ordered_capture_session_use_case
    ),
) -> OrderedCaptureSessionResponse:
    try:
        _require_ordered_capture_enabled()
        session = use_case.execute(session_id, principal=principal)
    except Exception as e:
        reraise_if_mapped(e)
        raise
    return ordered_capture_session_to_response(session)


@router.post(
    "/ordered-capture-sessions/{session_id}/seal",
    response_model=OrderedCaptureSessionResponse,
)
def seal_ordered_capture_session(
    session_id: str,
    body: SealOrderedCaptureSessionRequest,
    principal: AccessPrincipal = Depends(get_access_principal),
    use_case: SealOrderedCaptureSessionUseCase = Depends(
        get_seal_ordered_capture_session_use_case
    ),
) -> OrderedCaptureSessionResponse:
    try:
        _require_ordered_capture_enabled()
        session = use_case.execute(
            SealOrderedCaptureSessionCommand(
                session_id=session_id,
                expected_asset_count=body.expected_asset_count,
                sequence_version=body.sequence_version,
                principal=principal,
            )
        )
    except Exception as e:
        reraise_if_mapped(e)
        raise
    return ordered_capture_session_to_response(session)
