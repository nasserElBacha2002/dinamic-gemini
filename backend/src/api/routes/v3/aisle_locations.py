"""v3 aisle locations + positioning labels (CRUD, issue, render, replace, batch).

DEPRECATED for new product flows: prefer client-scoped
``/api/v3/clients/{client_id}/position-labels``. These inventory/aisle-rooted
routes remain temporarily for legacy consumers and emit Deprecation via docs.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status

from src.api.dependencies import (
    get_batch_render_aisle_location_labels_use_case,
    get_create_aisle_location_use_case,
    get_download_aisle_location_label_use_case,
    get_get_aisle_location_label_use_case,
    get_get_aisle_location_use_case,
    get_invalidate_aisle_location_label_use_case,
    get_issue_aisle_location_label_use_case,
    get_list_aisle_location_labels_use_case,
    get_list_aisle_locations_use_case,
    get_render_aisle_location_label_use_case,
    get_replace_aisle_location_label_use_case,
    get_update_aisle_location_use_case,
    require_inventory_client_scope,
)
from src.api.errors import reraise_if_mapped
from src.api.schemas.aisle_location_schemas import (
    AisleLocationLabelArtifactResponse,
    AisleLocationLabelListResponse,
    AisleLocationLabelResponse,
    AisleLocationListResponse,
    AisleLocationResponse,
    BatchRenderAisleLocationLabelsRequest,
    CreateAisleLocationRequest,
    InvalidateAisleLocationLabelRequest,
    IssueAisleLocationLabelRequest,
    RenderAisleLocationLabelRequest,
    ReplaceAisleLocationLabelRequest,
    UpdateAisleLocationRequest,
    aisle_location_label_artifact_to_response,
    aisle_location_label_to_response,
    aisle_location_to_response,
)
from src.api.schemas.listing_schemas import compute_total_pages
from src.application.dto.access_principal import AccessPrincipal
from src.application.errors import AisleLocationLabelConflictError, StrategyDisabledError
from src.application.use_cases.aisle_locations.manage_aisle_locations import (
    CreateAisleLocationCommand,
    CreateAisleLocationUseCase,
    GetAisleLocationCommand,
    GetAisleLocationUseCase,
    InvalidateAisleLocationLabelCommand,
    InvalidateAisleLocationLabelUseCase,
    IssueAisleLocationLabelCommand,
    IssueAisleLocationLabelUseCase,
    ListAisleLocationLabelsCommand,
    ListAisleLocationLabelsUseCase,
    ListAisleLocationsCommand,
    ListAisleLocationsUseCase,
    UpdateAisleLocationCommand,
    UpdateAisleLocationUseCase,
)
from src.config import load_settings
from src.domain.aisle_location.entities import AisleLocationStatus

router = APIRouter()


def _reject_legacy_positioning_writes() -> None:
    """Block new aisle-scoped positioning writes; client-scoped API is source of truth."""
    raise StrategyDisabledError(
        "AISLE_SCOPED_POSITIONING_WRITES_DISABLED: "
        "use POST /api/v3/clients/{client_id}/position-labels "
        "(removal after consumers migrate; read endpoints remain temporarily)"
    )


def _require_aisle_location_domain_enabled() -> None:
    if not load_settings().aisle_location_domain_enabled:
        raise StrategyDisabledError("AISLE_LOCATION_DOMAIN_ENABLED=false")


def _require_aisle_location_labels_enabled() -> None:
    if not load_settings().aisle_location_labels_enabled:
        raise StrategyDisabledError("AISLE_LOCATION_LABELS_ENABLED=false")


@router.post(
    "/{inventory_id}/aisles/{aisle_id}/locations",
    response_model=AisleLocationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_aisle_location(
    inventory_id: str,
    aisle_id: str,
    body: CreateAisleLocationRequest,
    principal: AccessPrincipal = Depends(require_inventory_client_scope),
    use_case: CreateAisleLocationUseCase = Depends(get_create_aisle_location_use_case),
) -> AisleLocationResponse:
    try:
        _reject_legacy_positioning_writes()
        _require_aisle_location_domain_enabled()
        location = use_case.execute(
            CreateAisleLocationCommand(
                inventory_id=inventory_id,
                aisle_id=aisle_id,
                code=body.code,
                principal=principal,
                display_name=body.display_name,
                description=body.description,
            )
        )
    except Exception as e:
        reraise_if_mapped(e)
        raise
    return aisle_location_to_response(location)


@router.get(
    "/{inventory_id}/aisles/{aisle_id}/locations",
    response_model=AisleLocationListResponse,
)
def list_aisle_locations(
    inventory_id: str,
    aisle_id: str,
    status_filter: str | None = Query(None, alias="status"),
    search: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    principal: AccessPrincipal = Depends(require_inventory_client_scope),
    use_case: ListAisleLocationsUseCase = Depends(get_list_aisle_locations_use_case),
) -> AisleLocationListResponse:
    try:
        _require_aisle_location_domain_enabled()
        offset = (page - 1) * page_size
        items, total = use_case.execute(
            ListAisleLocationsCommand(
                inventory_id=inventory_id,
                aisle_id=aisle_id,
                principal=principal,
                status=status_filter,
                search=search,
                limit=page_size,
                offset=offset,
            )
        )
    except Exception as e:
        reraise_if_mapped(e)
        raise
    return AisleLocationListResponse(
        items=[aisle_location_to_response(loc) for loc in items],
        page=page,
        page_size=page_size,
        total_items=total,
        total_pages=compute_total_pages(total, page_size),
    )


@router.get(
    "/{inventory_id}/aisles/{aisle_id}/locations/{location_id}",
    response_model=AisleLocationResponse,
)
def get_aisle_location(
    inventory_id: str,
    aisle_id: str,
    location_id: str,
    principal: AccessPrincipal = Depends(require_inventory_client_scope),
    use_case: GetAisleLocationUseCase = Depends(get_get_aisle_location_use_case),
) -> AisleLocationResponse:
    try:
        _require_aisle_location_domain_enabled()
        location = use_case.execute(
            GetAisleLocationCommand(
                inventory_id=inventory_id,
                location_id=location_id,
                principal=principal,
            )
        )
        if location.aisle_id != aisle_id:
            from src.application.errors import AisleLocationNotFoundError

            raise AisleLocationNotFoundError(location_id)
    except Exception as e:
        reraise_if_mapped(e)
        raise
    return aisle_location_to_response(location)


@router.patch(
    "/{inventory_id}/aisles/{aisle_id}/locations/{location_id}",
    response_model=AisleLocationResponse,
)
def update_aisle_location(
    inventory_id: str,
    aisle_id: str,
    location_id: str,
    body: UpdateAisleLocationRequest,
    principal: AccessPrincipal = Depends(require_inventory_client_scope),
    use_case: UpdateAisleLocationUseCase = Depends(get_update_aisle_location_use_case),
) -> AisleLocationResponse:
    try:
        _reject_legacy_positioning_writes()
        _require_aisle_location_domain_enabled()
        status_value = (
            AisleLocationStatus(body.status) if body.status is not None else None
        )
        location = use_case.execute(
            UpdateAisleLocationCommand(
                location_id=location_id,
                inventory_id=inventory_id,
                principal=principal,
                display_name=body.display_name,
                description=body.description,
                status=status_value,
            )
        )
        if location.aisle_id != aisle_id:
            from src.application.errors import AisleLocationNotFoundError

            raise AisleLocationNotFoundError(location_id)
    except Exception as e:
        reraise_if_mapped(e)
        raise
    return aisle_location_to_response(location)


@router.post(
    "/{inventory_id}/locations/{location_id}/labels",
    response_model=AisleLocationLabelResponse,
    status_code=status.HTTP_201_CREATED,
)
def issue_aisle_location_label(
    inventory_id: str,
    location_id: str,
    body: IssueAisleLocationLabelRequest | None = None,
    principal: AccessPrincipal = Depends(require_inventory_client_scope),
    use_case: IssueAisleLocationLabelUseCase = Depends(
        get_issue_aisle_location_label_use_case
    ),
) -> AisleLocationLabelResponse:
    try:
        _reject_legacy_positioning_writes()
        _require_aisle_location_domain_enabled()
        _require_aisle_location_labels_enabled()
        req = body or IssueAisleLocationLabelRequest(idempotency_key=None)
        label = use_case.execute(
            IssueAisleLocationLabelCommand(
                location_id=location_id,
                inventory_id=inventory_id,
                principal=principal,
                idempotency_key=req.idempotency_key,
            )
        )
    except Exception as e:
        reraise_if_mapped(e)
        raise
    return aisle_location_label_to_response(label)


@router.get(
    "/{inventory_id}/locations/{location_id}/labels",
    response_model=AisleLocationLabelListResponse,
)
def list_aisle_location_labels(
    inventory_id: str,
    location_id: str,
    status_filter: str | None = Query(None, alias="status"),
    principal: AccessPrincipal = Depends(require_inventory_client_scope),
    use_case: ListAisleLocationLabelsUseCase = Depends(
        get_list_aisle_location_labels_use_case
    ),
) -> AisleLocationLabelListResponse:
    try:
        _require_aisle_location_domain_enabled()
        _require_aisle_location_labels_enabled()
        labels = use_case.execute(
            ListAisleLocationLabelsCommand(
                inventory_id=inventory_id,
                location_id=location_id,
                principal=principal,
                status=status_filter,
            )
        )
    except Exception as e:
        reraise_if_mapped(e)
        raise
    return AisleLocationLabelListResponse(
        items=[aisle_location_label_to_response(lab) for lab in labels]
    )


@router.post(
    "/{inventory_id}/locations/{location_id}/labels/{label_id}/invalidate",
    response_model=AisleLocationLabelResponse,
)
def invalidate_aisle_location_label(
    inventory_id: str,
    location_id: str,
    label_id: str,
    body: InvalidateAisleLocationLabelRequest | None = None,
    principal: AccessPrincipal = Depends(require_inventory_client_scope),
    use_case: InvalidateAisleLocationLabelUseCase = Depends(
        get_invalidate_aisle_location_label_use_case
    ),
) -> AisleLocationLabelResponse:
    try:
        _reject_legacy_positioning_writes()
        _require_aisle_location_domain_enabled()
        _require_aisle_location_labels_enabled()
        req = body or InvalidateAisleLocationLabelRequest(reason=None)
        label = use_case.execute(
            InvalidateAisleLocationLabelCommand(
                label_id=label_id,
                inventory_id=inventory_id,
                principal=principal,
                reason=req.reason,
            )
        )
        if label.location_id != location_id:
            from src.application.errors import AisleLocationLabelNotFoundError

            raise AisleLocationLabelNotFoundError(label_id)
    except Exception as e:
        reraise_if_mapped(e)
        raise
    return aisle_location_label_to_response(label)


def _require_aisle_location_label_render_enabled() -> None:
    if not load_settings().aisle_location_label_render_enabled:
        raise StrategyDisabledError("AISLE_LOCATION_LABEL_RENDER_ENABLED=false")


@router.get(
    "/{inventory_id}/locations/{location_id}/labels/{label_id}",
    response_model=AisleLocationLabelResponse,
)
def get_aisle_location_label(
    inventory_id: str,
    location_id: str,
    label_id: str,
    principal: AccessPrincipal = Depends(require_inventory_client_scope),
    use_case=Depends(get_get_aisle_location_label_use_case),
) -> AisleLocationLabelResponse:
    from src.application.errors import AisleLocationLabelNotFoundError
    from src.application.use_cases.aisle_locations.render_aisle_location_labels import (
        GetAisleLocationLabelCommand,
    )

    try:
        _require_aisle_location_domain_enabled()
        _require_aisle_location_labels_enabled()
        label = use_case.execute(
            GetAisleLocationLabelCommand(
                inventory_id=inventory_id,
                label_id=label_id,
                principal=principal,
            )
        )
        if label.location_id != location_id:
            raise AisleLocationLabelNotFoundError(label_id)
    except Exception as e:
        reraise_if_mapped(e)
        raise
    return aisle_location_label_to_response(label)


@router.post(
    "/{inventory_id}/labels/{label_id}/render",
    response_model=AisleLocationLabelArtifactResponse,
    status_code=status.HTTP_201_CREATED,
)
def render_aisle_location_label(
    inventory_id: str,
    label_id: str,
    body: RenderAisleLocationLabelRequest,
    principal: AccessPrincipal = Depends(require_inventory_client_scope),
    use_case=Depends(get_render_aisle_location_label_use_case),
) -> AisleLocationLabelArtifactResponse:
    from src.application.use_cases.aisle_locations.render_aisle_location_labels import (
        RenderAisleLocationLabelCommand,
    )

    try:
        _require_aisle_location_domain_enabled()
        _require_aisle_location_labels_enabled()
        _require_aisle_location_label_render_enabled()
        artifact = use_case.execute(
            RenderAisleLocationLabelCommand(
                inventory_id=inventory_id,
                label_id=label_id,
                principal=principal,
                format=body.format,  # type: ignore[arg-type]
                preset=body.preset,
            )
        )
    except Exception as e:
        reraise_if_mapped(e)
        raise
    return aisle_location_label_artifact_to_response(artifact)


@router.get("/{inventory_id}/labels/{label_id}/preview")
def preview_aisle_location_label(
    inventory_id: str,
    label_id: str,
    format: str = Query("PNG"),
    preset: str = Query("MM_100x100"),
    principal: AccessPrincipal = Depends(require_inventory_client_scope),
    use_case=Depends(get_download_aisle_location_label_use_case),
):
    from fastapi.responses import Response

    from src.application.use_cases.aisle_locations.render_aisle_location_labels import (
        DownloadAisleLocationLabelCommand,
    )

    try:
        _require_aisle_location_domain_enabled()
        _require_aisle_location_labels_enabled()
        _require_aisle_location_label_render_enabled()
        fmt = format.upper()
        if fmt not in ("PDF", "PNG"):
            raise AisleLocationLabelConflictError(
                "format must be PDF or PNG",
                code="POSITION_LABEL_FORMAT_UNSUPPORTED",
            )
        result = use_case.execute(
            DownloadAisleLocationLabelCommand(
                inventory_id=inventory_id,
                label_id=label_id,
                principal=principal,
                format=fmt,  # type: ignore[arg-type]
                preset=preset,
            )
        )
    except Exception as e:
        reraise_if_mapped(e)
        raise
    return Response(
        content=result.content,
        media_type=result.artifact.content_type,
        headers={"Content-Disposition": f'inline; filename="{result.filename}"'},
    )


@router.get("/{inventory_id}/labels/{label_id}/download")
def download_aisle_location_label(
    inventory_id: str,
    label_id: str,
    format: str = Query("PDF"),
    preset: str = Query("MM_100x100"),
    principal: AccessPrincipal = Depends(require_inventory_client_scope),
    use_case=Depends(get_download_aisle_location_label_use_case),
):
    from fastapi.responses import Response

    from src.application.use_cases.aisle_locations.render_aisle_location_labels import (
        DownloadAisleLocationLabelCommand,
    )

    try:
        _require_aisle_location_domain_enabled()
        _require_aisle_location_labels_enabled()
        _require_aisle_location_label_render_enabled()
        fmt = format.upper()
        if fmt not in ("PDF", "PNG"):
            raise AisleLocationLabelConflictError(
                "format must be PDF or PNG",
                code="POSITION_LABEL_FORMAT_UNSUPPORTED",
            )
        result = use_case.execute(
            DownloadAisleLocationLabelCommand(
                inventory_id=inventory_id,
                label_id=label_id,
                principal=principal,
                format=fmt,  # type: ignore[arg-type]
                preset=preset,
            )
        )
    except Exception as e:
        reraise_if_mapped(e)
        raise
    return Response(
        content=result.content,
        media_type=result.artifact.content_type,
        headers={"Content-Disposition": f'attachment; filename="{result.filename}"'},
    )


@router.post(
    "/{inventory_id}/labels/{label_id}/replace",
    response_model=AisleLocationLabelResponse,
)
def replace_aisle_location_label(
    inventory_id: str,
    label_id: str,
    body: ReplaceAisleLocationLabelRequest | None = None,
    principal: AccessPrincipal = Depends(require_inventory_client_scope),
    use_case=Depends(get_replace_aisle_location_label_use_case),
) -> AisleLocationLabelResponse:
    from src.application.use_cases.aisle_locations.render_aisle_location_labels import (
        ReplaceAisleLocationLabelCommand,
    )

    try:
        _reject_legacy_positioning_writes()
        _require_aisle_location_domain_enabled()
        _require_aisle_location_labels_enabled()
        req = body or ReplaceAisleLocationLabelRequest(idempotency_key=None)
        label = use_case.execute(
            ReplaceAisleLocationLabelCommand(
                inventory_id=inventory_id,
                label_id=label_id,
                principal=principal,
                idempotency_key=req.idempotency_key,
            )
        )
    except Exception as e:
        reraise_if_mapped(e)
        raise
    return aisle_location_label_to_response(label)


@router.post("/{inventory_id}/aisles/{aisle_id}/labels/batch-render")
def batch_render_aisle_location_labels(
    inventory_id: str,
    aisle_id: str,
    body: BatchRenderAisleLocationLabelsRequest,
    principal: AccessPrincipal = Depends(require_inventory_client_scope),
    use_case=Depends(get_batch_render_aisle_location_labels_use_case),
):
    from fastapi.responses import Response

    from src.application.use_cases.aisle_locations.render_aisle_location_labels import (
        BatchRenderAisleLocationLabelsCommand,
    )

    try:
        _reject_legacy_positioning_writes()
        _require_aisle_location_domain_enabled()
        _require_aisle_location_labels_enabled()
        _require_aisle_location_label_render_enabled()
        result = use_case.execute(
            BatchRenderAisleLocationLabelsCommand(
                inventory_id=inventory_id,
                aisle_id=aisle_id,
                principal=principal,
                preset=body.preset,
                format=body.format,  # type: ignore[arg-type]
                location_ids=tuple(body.location_ids) if body.location_ids else None,
                emit_missing=bool(body.emit_missing),
                idempotency_key=body.idempotency_key,
            )
        )
    except Exception as e:
        reraise_if_mapped(e)
        raise
    return Response(
        content=result.content,
        media_type=result.artifact.content_type,
        headers={"Content-Disposition": f'attachment; filename="{result.filename}"'},
    )
