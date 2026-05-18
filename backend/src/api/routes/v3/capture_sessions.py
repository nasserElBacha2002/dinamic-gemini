"""v3 field capture sessions — Sprint 2 + Sprint 3 (clock offset, assignment preview, time metadata)."""

from __future__ import annotations

from datetime import datetime
from io import BytesIO

from fastapi import APIRouter, Depends, File, Query, UploadFile, status

from src.api.dependencies import (
    get_assign_capture_session_group_to_existing_aisle_use_case,
    get_cancel_capture_session_use_case,
    get_close_capture_session_use_case,
    get_compute_capture_session_assignment_preview_use_case,
    get_compute_capture_session_groups_use_case,
    get_compute_materialized_capture_session_group_preview_use_case,
    get_create_aisle_and_assign_capture_session_group_use_case,
    get_create_capture_session_use_case,
    get_get_capture_session_detail_use_case,
    get_get_capture_session_groups_use_case,
    get_list_capture_sessions_use_case,
    get_materialize_capture_session_group_use_case,
    get_materialize_capture_session_use_case,
    get_update_capture_session_clock_offset_use_case,
    get_upload_capture_session_staging_items_use_case,
)
from src.api.errors import reraise_if_mapped
from src.api.schemas.capture_schemas import (
    AssignCaptureSessionGroupToExistingAisleRequest,
    CaptureSessionClockOffsetUpdateRequest,
    CaptureSessionDetailResponse,
    CaptureSessionGroupsListResponse,
    CaptureSessionMaterializeRequest,
    CaptureSessionResponse,
    CaptureSessionStagingUploadFileError,
    CreateAisleFromCaptureGroupRequest,
    MaterializeAllCaptureSessionGroupsResponse,
    MaterializeCaptureSessionGroupResponse,
    MaterializeCaptureSessionResponse,
    MaterializedCaptureSessionGroupPreviewResponse,
    PaginatedCaptureSessionListResponse,
    UploadCaptureSessionItemsResponse,
    capture_session_groups_to_response,
    capture_session_item_to_response,
    capture_session_to_response,
    materialized_capture_session_group_preview_to_response,
)
from src.api.schemas.listing_schemas import compute_total_pages
from src.application.dto.uploaded_file import UploadedFile
from src.application.services.capture_session_status_filter import (
    parse_capture_session_status_filter,
)
from src.application.services.upload_file_count_validation import (
    assert_upload_file_count_within_limit,
)
from src.application.use_cases.assign_capture_session_group_to_existing_aisle import (
    AssignCaptureSessionGroupToExistingAisleUseCase,
)
from src.application.use_cases.cancel_capture_session import CancelCaptureSessionUseCase
from src.application.use_cases.close_capture_session import CloseCaptureSessionUseCase
from src.application.use_cases.compute_capture_session_assignment_preview import (
    ComputeCaptureSessionAssignmentPreviewUseCase,
)
from src.application.use_cases.compute_capture_session_groups import (
    ComputeCaptureSessionGroupsUseCase,
)
from src.application.use_cases.compute_materialized_capture_session_group_preview import (
    ComputeMaterializedCaptureSessionGroupPreviewUseCase,
)
from src.application.use_cases.create_aisle_and_assign_capture_session_group import (
    CreateAisleAndAssignCaptureSessionGroupUseCase,
)
from src.application.use_cases.create_capture_session import CreateCaptureSessionUseCase
from src.application.use_cases.get_capture_session_detail import (
    CaptureSessionDetailResult,
    GetCaptureSessionDetailUseCase,
)
from src.application.use_cases.get_capture_session_groups import GetCaptureSessionGroupsUseCase
from src.application.use_cases.list_capture_sessions import ListCaptureSessionsUseCase
from src.application.use_cases.materialize_capture_session import (
    MaterializeCaptureSessionResult,
    MaterializeCaptureSessionUseCase,
)
from src.application.use_cases.materialize_capture_session_group import (
    MaterializeCaptureSessionGroupUseCase,
)
from src.application.use_cases.update_capture_session_clock_offset import (
    UpdateCaptureSessionClockOffsetUseCase,
)
from src.application.use_cases.upload_capture_session_staging_items import (
    StagingUploadBatchResult,
    UploadCaptureSessionStagingItemsUseCase,
)

router = APIRouter()


def _capture_session_detail_response(
    detail: CaptureSessionDetailResult,
) -> CaptureSessionDetailResponse:
    return CaptureSessionDetailResponse(
        session=capture_session_to_response(detail.session),
        items=[capture_session_item_to_response(i) for i in detail.items],
    )


def _materialize_capture_session_http_response(
    detail: CaptureSessionDetailResult,
    out: MaterializeCaptureSessionResult,
) -> MaterializeCaptureSessionResponse:
    return MaterializeCaptureSessionResponse(
        session=capture_session_to_response(detail.session),
        items=[capture_session_item_to_response(i) for i in detail.items],
        created_assets_count=len(out.created_asset_ids),
    )


def _staging_upload_batch_response(
    batch: StagingUploadBatchResult,
) -> UploadCaptureSessionItemsResponse:
    return UploadCaptureSessionItemsResponse(
        items=[capture_session_item_to_response(i) for i in batch.items],
        errors=[
            CaptureSessionStagingUploadFileError(
                filename=e.filename,
                code=e.code,
                detail=e.detail,
                file_index=e.file_index,
            )
            for e in batch.errors
        ],
    )


async def _upload_files_to_staging_dtos(files: list[UploadFile]) -> list[UploadedFile]:
    assert_upload_file_count_within_limit(len(files))
    uploaded: list[UploadedFile] = []
    for u in files:
        content = await u.read()
        uploaded.append(
            UploadedFile(
                original_filename=u.filename or "file",
                file_obj=BytesIO(content),
                content_type=u.content_type or "application/octet-stream",
            )
        )
    return uploaded


@router.post(
    "/{inventory_id}/capture-sessions",
    response_model=CaptureSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_inventory_capture_session(
    inventory_id: str,
    use_case: CreateCaptureSessionUseCase = Depends(get_create_capture_session_use_case),
) -> CaptureSessionResponse:
    try:
        session = use_case.execute(inventory_id=inventory_id, aisle_id=None)
    except Exception as e:
        reraise_if_mapped(e)
        raise
    return capture_session_to_response(session)


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
        session = use_case.execute(inventory_id=inventory_id, aisle_id=aisle_id)
    except Exception as e:
        reraise_if_mapped(e)
        raise
    return capture_session_to_response(session)


@router.post(
    "/{inventory_id}/capture-sessions/{session_id}/close",
    response_model=CaptureSessionDetailResponse,
)
def close_capture_session_inventory_scope(
    inventory_id: str,
    session_id: str,
    use_case: CloseCaptureSessionUseCase = Depends(get_close_capture_session_use_case),
    detail_uc: GetCaptureSessionDetailUseCase = Depends(get_get_capture_session_detail_use_case),
) -> CaptureSessionDetailResponse:
    try:
        use_case.execute(inventory_id=inventory_id, session_id=session_id, aisle_id=None)
        detail = detail_uc.execute(inventory_id, session_id)
    except Exception as e:
        reraise_if_mapped(e)
        raise
    return _capture_session_detail_response(detail)


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
    return _capture_session_detail_response(detail)


@router.post(
    "/{inventory_id}/capture-sessions/{session_id}/cancel",
    response_model=CaptureSessionDetailResponse,
)
def cancel_capture_session_inventory_scope(
    inventory_id: str,
    session_id: str,
    use_case: CancelCaptureSessionUseCase = Depends(get_cancel_capture_session_use_case),
    detail_uc: GetCaptureSessionDetailUseCase = Depends(get_get_capture_session_detail_use_case),
) -> CaptureSessionDetailResponse:
    try:
        use_case.execute(inventory_id=inventory_id, session_id=session_id, aisle_id=None)
        detail = detail_uc.execute(inventory_id, session_id)
    except Exception as e:
        reraise_if_mapped(e)
        raise
    return _capture_session_detail_response(detail)


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
    return _capture_session_detail_response(detail)


@router.get(
    "/{inventory_id}/capture-sessions",
    response_model=PaginatedCaptureSessionListResponse,
)
def list_capture_sessions(
    inventory_id: str,
    aisle_id: str | None = Query(None, description="Optional aisle id filter."),
    status: str | None = Query(
        None,
        description="Comma-separated session statuses (e.g. draft,importing,cancelled).",
    ),
    created_from: datetime | None = Query(None),
    created_to: datetime | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int | None = Query(None, ge=1),
    use_case: ListCaptureSessionsUseCase = Depends(get_list_capture_sessions_use_case),
) -> PaginatedCaptureSessionListResponse:
    try:
        statuses = parse_capture_session_status_filter(status)
        result = use_case.execute(
            inventory_id,
            aisle_id=aisle_id,
            statuses=statuses,
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


@router.patch(
    "/{inventory_id}/aisles/{aisle_id}/capture-sessions/{session_id}/clock-offset",
    response_model=CaptureSessionDetailResponse,
)
def patch_capture_session_clock_offset(
    inventory_id: str,
    aisle_id: str,
    session_id: str,
    body: CaptureSessionClockOffsetUpdateRequest,
    use_case: UpdateCaptureSessionClockOffsetUseCase = Depends(
        get_update_capture_session_clock_offset_use_case
    ),
    detail_uc: GetCaptureSessionDetailUseCase = Depends(get_get_capture_session_detail_use_case),
) -> CaptureSessionDetailResponse:
    try:
        use_case.execute(
            inventory_id=inventory_id,
            aisle_id=aisle_id,
            session_id=session_id,
            clock_offset_seconds=body.clock_offset_seconds,
        )
        detail = detail_uc.execute(inventory_id, session_id)
    except Exception as e:
        reraise_if_mapped(e)
        raise
    return _capture_session_detail_response(detail)


@router.post(
    "/{inventory_id}/aisles/{aisle_id}/capture-sessions/{session_id}/preview-assignment",
    response_model=CaptureSessionDetailResponse,
)
def post_capture_session_preview_assignment(
    inventory_id: str,
    aisle_id: str,
    session_id: str,
    use_case: ComputeCaptureSessionAssignmentPreviewUseCase = Depends(
        get_compute_capture_session_assignment_preview_use_case
    ),
    detail_uc: GetCaptureSessionDetailUseCase = Depends(get_get_capture_session_detail_use_case),
) -> CaptureSessionDetailResponse:
    try:
        use_case.execute(inventory_id=inventory_id, aisle_id=aisle_id, session_id=session_id)
        detail = detail_uc.execute(inventory_id, session_id)
    except Exception as e:
        reraise_if_mapped(e)
        raise
    return _capture_session_detail_response(detail)


@router.post(
    "/{inventory_id}/aisles/{aisle_id}/capture-sessions/{session_id}/materialize",
    response_model=MaterializeCaptureSessionResponse,
)
def post_capture_session_materialize(
    inventory_id: str,
    aisle_id: str,
    session_id: str,
    body: CaptureSessionMaterializeRequest,
    use_case: MaterializeCaptureSessionUseCase = Depends(get_materialize_capture_session_use_case),
    detail_uc: GetCaptureSessionDetailUseCase = Depends(get_get_capture_session_detail_use_case),
) -> MaterializeCaptureSessionResponse:
    try:
        out = use_case.execute(
            inventory_id=inventory_id,
            aisle_id=aisle_id,
            session_id=session_id,
            idempotency_key=body.idempotency_key,
        )
        detail = detail_uc.execute(inventory_id, session_id)
    except Exception as e:
        reraise_if_mapped(e)
        raise
    return _materialize_capture_session_http_response(detail, out)


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
    return _capture_session_detail_response(detail)


@router.post(
    "/{inventory_id}/capture-sessions/{session_id}/compute-groups",
    response_model=CaptureSessionGroupsListResponse,
    status_code=status.HTTP_200_OK,
)
def compute_capture_session_groups_inventory_scope(
    inventory_id: str,
    session_id: str,
    use_case: ComputeCaptureSessionGroupsUseCase = Depends(
        get_compute_capture_session_groups_use_case
    ),
) -> CaptureSessionGroupsListResponse:
    try:
        summaries = use_case.execute(inventory_id=inventory_id, session_id=session_id)
    except Exception as e:
        reraise_if_mapped(e)
        raise
    return capture_session_groups_to_response(summaries)


@router.get(
    "/{inventory_id}/capture-sessions/{session_id}/groups",
    response_model=CaptureSessionGroupsListResponse,
)
def list_capture_session_groups_inventory_scope(
    inventory_id: str,
    session_id: str,
    use_case: GetCaptureSessionGroupsUseCase = Depends(get_get_capture_session_groups_use_case),
) -> CaptureSessionGroupsListResponse:
    try:
        summaries = use_case.execute(inventory_id=inventory_id, session_id=session_id)
    except Exception as e:
        reraise_if_mapped(e)
        raise
    return capture_session_groups_to_response(summaries)


@router.post(
    "/{inventory_id}/capture-sessions/{session_id}/groups/{group_id}/assign-existing",
    response_model=CaptureSessionGroupsListResponse,
    status_code=status.HTTP_200_OK,
)
def assign_capture_session_group_to_existing_aisle_inventory_scope(
    inventory_id: str,
    session_id: str,
    group_id: str,
    body: AssignCaptureSessionGroupToExistingAisleRequest,
    use_case: AssignCaptureSessionGroupToExistingAisleUseCase = Depends(
        get_assign_capture_session_group_to_existing_aisle_use_case
    ),
) -> CaptureSessionGroupsListResponse:
    try:
        summaries = use_case.execute(
            inventory_id=inventory_id,
            session_id=session_id,
            group_id=group_id,
            aisle_id=body.aisle_id,
        )
    except Exception as e:
        reraise_if_mapped(e)
        raise
    return capture_session_groups_to_response(summaries)


@router.post(
    "/{inventory_id}/capture-sessions/{session_id}/groups/{group_id}/create-aisle",
    response_model=CaptureSessionGroupsListResponse,
    status_code=status.HTTP_200_OK,
)
def create_aisle_and_assign_capture_session_group_inventory_scope(
    inventory_id: str,
    session_id: str,
    group_id: str,
    body: CreateAisleFromCaptureGroupRequest,
    use_case: CreateAisleAndAssignCaptureSessionGroupUseCase = Depends(
        get_create_aisle_and_assign_capture_session_group_use_case
    ),
) -> CaptureSessionGroupsListResponse:
    try:
        summaries = use_case.execute(
            inventory_id=inventory_id,
            session_id=session_id,
            group_id=group_id,
            aisle_code=body.code,
            client_supplier_id=body.client_supplier_id,
        )
    except Exception as e:
        reraise_if_mapped(e)
        raise
    return capture_session_groups_to_response(summaries)


@router.post(
    "/{inventory_id}/capture-sessions/{session_id}/groups/materialize",
    response_model=MaterializeAllCaptureSessionGroupsResponse,
    status_code=status.HTTP_200_OK,
)
def post_materialize_all_assigned_capture_session_groups(
    inventory_id: str,
    session_id: str,
    use_case: MaterializeCaptureSessionGroupUseCase = Depends(
        get_materialize_capture_session_group_use_case
    ),
) -> MaterializeAllCaptureSessionGroupsResponse:
    try:
        out = use_case.materialize_all_assigned(inventory_id=inventory_id, session_id=session_id)
    except Exception as e:
        reraise_if_mapped(e)
        raise
    return MaterializeAllCaptureSessionGroupsResponse(
        total_groups=out.total_groups,
        materialized_groups=out.materialized_groups,
        skipped_groups=out.skipped_groups,
        total_assets_created=out.total_assets_created,
        total_assets_skipped=out.total_assets_skipped,
        total_assets_failed=out.total_assets_failed,
    )


@router.post(
    "/{inventory_id}/capture-sessions/{session_id}/groups/{group_id}/materialize",
    response_model=MaterializeCaptureSessionGroupResponse,
    status_code=status.HTTP_200_OK,
)
def post_materialize_capture_session_group(
    inventory_id: str,
    session_id: str,
    group_id: str,
    use_case: MaterializeCaptureSessionGroupUseCase = Depends(
        get_materialize_capture_session_group_use_case
    ),
) -> MaterializeCaptureSessionGroupResponse:
    try:
        out = use_case.materialize_one(
            inventory_id=inventory_id, session_id=session_id, group_id=group_id
        )
    except Exception as e:
        reraise_if_mapped(e)
        raise
    return MaterializeCaptureSessionGroupResponse(
        group_id=out.group_id,
        aisle_id=out.aisle_id,
        created_assets=out.created_assets,
        skipped_assets=out.skipped_assets,
        failed_assets=out.failed_assets,
        status=out.status,
    )


@router.post(
    "/{inventory_id}/capture-sessions/{session_id}/groups/{group_id}/preview",
    response_model=MaterializedCaptureSessionGroupPreviewResponse,
    status_code=status.HTTP_200_OK,
)
def post_materialized_capture_session_group_preview(
    inventory_id: str,
    session_id: str,
    group_id: str,
    use_case: ComputeMaterializedCaptureSessionGroupPreviewUseCase = Depends(
        get_compute_materialized_capture_session_group_preview_use_case
    ),
) -> MaterializedCaptureSessionGroupPreviewResponse:
    try:
        result = use_case.execute(
            inventory_id=inventory_id, session_id=session_id, group_id=group_id
        )
    except Exception as e:
        reraise_if_mapped(e)
        raise
    return materialized_capture_session_group_preview_to_response(result)


@router.post(
    "/{inventory_id}/capture-sessions/{session_id}/items",
    response_model=UploadCaptureSessionItemsResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_capture_session_staging_items_inventory_scope(
    inventory_id: str,
    session_id: str,
    files: list[UploadFile] = File(...),
    use_case: UploadCaptureSessionStagingItemsUseCase = Depends(
        get_upload_capture_session_staging_items_use_case
    ),
) -> UploadCaptureSessionItemsResponse:
    try:
        uploaded = await _upload_files_to_staging_dtos(files)
    except Exception as e:
        reraise_if_mapped(e)
        raise
    try:
        batch = use_case.execute(
            inventory_id=inventory_id,
            aisle_id=None,
            session_id=session_id,
            files=uploaded,
        )
    except Exception as e:
        reraise_if_mapped(e)
        raise
    return _staging_upload_batch_response(batch)


@router.post(
    "/{inventory_id}/aisles/{aisle_id}/capture-sessions/{session_id}/items",
    response_model=UploadCaptureSessionItemsResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_capture_session_staging_items(
    inventory_id: str,
    aisle_id: str,
    session_id: str,
    files: list[UploadFile] = File(...),
    use_case: UploadCaptureSessionStagingItemsUseCase = Depends(
        get_upload_capture_session_staging_items_use_case
    ),
) -> UploadCaptureSessionItemsResponse:
    """Stage files for a capture session.

    Same buffering pattern as ``upload_aisle_assets``: each ``UploadFile`` is read fully into
    memory before invoking the use case (``BytesIO`` per file). Low-risk for typical capture
    batch sizes; very large files still hit ``max_upload_size_mb`` in the use case.
    """
    try:
        uploaded = await _upload_files_to_staging_dtos(files)
    except Exception as e:
        reraise_if_mapped(e)
        raise
    try:
        batch = use_case.execute(
            inventory_id=inventory_id,
            aisle_id=aisle_id,
            session_id=session_id,
            files=uploaded,
        )
    except Exception as e:
        reraise_if_mapped(e)
        raise
    return _staging_upload_batch_response(batch)
