"""v3 field capture sessions — Sprint 2 (create/close/cancel/list/detail/staging upload)."""

from __future__ import annotations

import logging
from datetime import datetime
from io import BytesIO
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status

from src.api.constants.error_wire import HTTP_DETAIL_AT_LEAST_ONE_FILE_REQUIRED
from src.api.dependencies import (
    get_cancel_capture_session_use_case,
    get_close_capture_session_use_case,
    get_create_capture_session_use_case,
    get_get_capture_session_detail_use_case,
    get_list_capture_sessions_use_case,
    get_upload_capture_session_staging_items_use_case,
)
from src.api.errors import reraise_if_mapped
from src.api.schemas.capture_schemas import (
    CaptureSessionDetailResponse,
    CaptureSessionResponse,
    PaginatedCaptureSessionListResponse,
    UploadCaptureSessionItemsResponse,
    capture_session_item_to_response,
    capture_session_to_response,
)
from src.api.schemas.listing_schemas import compute_total_pages
from src.application.dto.uploaded_file import UploadedFile
from src.application.use_cases.cancel_capture_session import CancelCaptureSessionUseCase
from src.application.use_cases.close_capture_session import CloseCaptureSessionUseCase
from src.application.use_cases.create_capture_session import CreateCaptureSessionUseCase
from src.application.use_cases.get_capture_session_detail import GetCaptureSessionDetailUseCase
from src.application.use_cases.list_capture_sessions import ListCaptureSessionsUseCase
from src.application.use_cases.upload_capture_session_staging_items import UploadCaptureSessionStagingItemsUseCase
from src.domain.capture.entities import CaptureSessionStatus

logger = logging.getLogger(__name__)

router = APIRouter()


def _parse_status_filter(raw: Optional[str]) -> Optional[List[CaptureSessionStatus]]:
    if not raw or not raw.strip():
        return None
    out: List[CaptureSessionStatus] = []
    for part in raw.split(","):
        p = part.strip().lower()
        if not p:
            continue
        try:
            out.append(CaptureSessionStatus(p))
        except ValueError:
            logger.debug("Ignoring unknown capture session status filter: %r", part)
    return out or None


@router.post(
    "/{inventory_id}/aisles/{aisle_id}/capture-sessions",
    response_model=CaptureSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_capture_session(
    inventory_id: str,
    aisle_id: str,
    use_case: CreateCaptureSessionUseCase = Depends(get_create_capture_session_use_case),
) -> CaptureSessionResponse:
    try:
        session = use_case.execute(inventory_id, aisle_id)
    except Exception as e:
        reraise_if_mapped(e)
        raise
    return capture_session_to_response(session)


@router.post(
    "/{inventory_id}/aisles/{aisle_id}/capture-sessions/{session_id}/close",
    response_model=CaptureSessionDetailResponse,
)
def close_capture_session(
    inventory_id: str,
    aisle_id: str,
    session_id: str,
    use_case: CloseCaptureSessionUseCase = Depends(get_close_capture_session_use_case),
    detail_uc: GetCaptureSessionDetailUseCase = Depends(get_get_capture_session_detail_use_case),
) -> CaptureSessionDetailResponse:
    try:
        use_case.execute(inventory_id=inventory_id, aisle_id=aisle_id, session_id=session_id)
        detail = detail_uc.execute(inventory_id, session_id)
    except Exception as e:
        reraise_if_mapped(e)
        raise
    return CaptureSessionDetailResponse(
        session=capture_session_to_response(detail.session),
        items=[capture_session_item_to_response(i) for i in detail.items],
    )


@router.post(
    "/{inventory_id}/aisles/{aisle_id}/capture-sessions/{session_id}/cancel",
    response_model=CaptureSessionDetailResponse,
)
def cancel_capture_session(
    inventory_id: str,
    aisle_id: str,
    session_id: str,
    use_case: CancelCaptureSessionUseCase = Depends(get_cancel_capture_session_use_case),
    detail_uc: GetCaptureSessionDetailUseCase = Depends(get_get_capture_session_detail_use_case),
) -> CaptureSessionDetailResponse:
    try:
        use_case.execute(inventory_id=inventory_id, aisle_id=aisle_id, session_id=session_id)
        detail = detail_uc.execute(inventory_id, session_id)
    except Exception as e:
        reraise_if_mapped(e)
        raise
    return CaptureSessionDetailResponse(
        session=capture_session_to_response(detail.session),
        items=[capture_session_item_to_response(i) for i in detail.items],
    )


@router.get(
    "/{inventory_id}/capture-sessions",
    response_model=PaginatedCaptureSessionListResponse,
)
def list_capture_sessions(
    inventory_id: str,
    aisle_id: Optional[str] = Query(None, description="Optional aisle id filter."),
    status: Optional[str] = Query(
        None,
        description="Comma-separated session statuses (e.g. draft,importing,cancelled).",
    ),
    created_from: Optional[datetime] = Query(None),
    created_to: Optional[datetime] = Query(None),
    page: int = Query(1, ge=1),
    page_size: Optional[int] = Query(None, ge=1),
    use_case: ListCaptureSessionsUseCase = Depends(get_list_capture_sessions_use_case),
) -> PaginatedCaptureSessionListResponse:
    try:
        result = use_case.execute(
            inventory_id,
            aisle_id=aisle_id,
            statuses=_parse_status_filter(status),
            created_from=created_from,
            created_to=created_to,
            page=page,
            page_size=page_size,
        )
    except Exception as e:
        reraise_if_mapped(e)
        raise
    total_pages = compute_total_pages(result.total_items, result.page_size)
    return PaginatedCaptureSessionListResponse(
        page=result.page,
        page_size=result.page_size,
        total_items=result.total_items,
        total_pages=total_pages,
        items=[capture_session_to_response(s) for s in result.items],
    )


@router.get(
    "/{inventory_id}/capture-sessions/{session_id}",
    response_model=CaptureSessionDetailResponse,
)
def get_capture_session_detail(
    inventory_id: str,
    session_id: str,
    use_case: GetCaptureSessionDetailUseCase = Depends(get_get_capture_session_detail_use_case),
) -> CaptureSessionDetailResponse:
    try:
        detail = use_case.execute(inventory_id, session_id)
    except Exception as e:
        reraise_if_mapped(e)
        raise
    return CaptureSessionDetailResponse(
        session=capture_session_to_response(detail.session),
        items=[capture_session_item_to_response(i) for i in detail.items],
    )


@router.post(
    "/{inventory_id}/aisles/{aisle_id}/capture-sessions/{session_id}/items",
    response_model=UploadCaptureSessionItemsResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_capture_session_staging_items(
    inventory_id: str,
    aisle_id: str,
    session_id: str,
    files: List[UploadFile] = File(...),
    use_case: UploadCaptureSessionStagingItemsUseCase = Depends(get_upload_capture_session_staging_items_use_case),
) -> UploadCaptureSessionItemsResponse:
    if not files:
        raise HTTPException(status_code=422, detail=HTTP_DETAIL_AT_LEAST_ONE_FILE_REQUIRED)
    uploaded: List[UploadedFile] = []
    for u in files:
        content = await u.read()
        uploaded.append(
            UploadedFile(
                original_filename=u.filename or "file",
                file_obj=BytesIO(content),
                content_type=u.content_type or "application/octet-stream",
            )
        )
    try:
        items = use_case.execute(
            inventory_id=inventory_id,
            aisle_id=aisle_id,
            session_id=session_id,
            files=uploaded,
        )
    except Exception as e:
        reraise_if_mapped(e)
        raise
    return UploadCaptureSessionItemsResponse(items=[capture_session_item_to_response(i) for i in items])
