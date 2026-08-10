"""Client-scoped positioning labels API (no inventory/aisle ownership)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Query, Response, status
from fastapi.responses import Response as FastAPIResponse

from src.api.dependencies import get_access_principal, get_client_repo, get_clock
from src.api.errors import reraise_if_mapped
from src.api.schemas.client_position_label_schemas import (
    ClientPositionLabelArtifactResponse,
    ClientPositionLabelListResponse,
    ClientPositionLabelMarkerSetResponse,
    ClientPositionLabelResponse,
    CreateClientPositionLabelRequest,
    CreateClientPositionMarkerSetRequest,
    InvalidateClientPositionLabelRequest,
    RenderClientPositionLabelRequest,
    UpdateClientPositionLabelRequest,
    client_position_label_to_response,
)
from src.api.schemas.listing_schemas import compute_total_pages
from src.application.dto.access_principal import AccessPrincipal
from src.application.errors import StrategyDisabledError
from src.application.ports.clock import Clock
from src.application.ports.repositories import ClientRepository
from src.application.services.positioning_label_renderer import PositioningLabelRenderer
from src.application.services.positioning_label_signing import (
    PositioningLabelSigningConfig,
    PositioningLabelSigningService,
    parse_previous_secrets,
)
from src.application.use_cases.client_position_labels import (
    CreateClientPositionLabelCommand,
    CreateClientPositionLabelUseCase,
    CreateClientPositionMarkerSetCommand,
    CreateClientPositionMarkerSetUseCase,
    DownloadClientPositionLabelUseCase,
    GetClientPositionLabelCommand,
    GetClientPositionLabelUseCase,
    InvalidateClientPositionLabelCommand,
    InvalidateClientPositionLabelUseCase,
    ListClientPositionLabelsCommand,
    ListClientPositionLabelsUseCase,
    RenderClientPositionLabelCommand,
    RenderClientPositionLabelUseCase,
    UpdateClientPositionLabelMetadataCommand,
    UpdateClientPositionLabelMetadataUseCase,
)
from src.config import load_settings
from src.runtime.app_container import get_app_container

router = APIRouter(tags=["client-position-labels"])


def _require_position_labels_enabled() -> None:
    if not load_settings().position_labels_enabled:
        raise StrategyDisabledError("POSITION_LABELS_ENABLED=false")


def _require_position_label_render_enabled() -> None:
    if not load_settings().position_label_render_enabled:
        raise StrategyDisabledError("POSITION_LABEL_RENDER_ENABLED=false")


def _get_label_repo():
    return get_app_container().get_client_position_label_repo()


def _signing_service() -> PositioningLabelSigningService:
    settings = load_settings()
    return PositioningLabelSigningService(
        PositioningLabelSigningConfig(
            secret=settings.positioning_label_hmac_secret or None,
            key_version=int(settings.positioning_label_hmac_key_version),
            previous_secrets=parse_previous_secrets(
                settings.positioning_label_hmac_previous_secrets
            ),
            required=bool(settings.positioning_label_signing_required),
        )
    )


def get_create_client_position_label_use_case(
    label_repo=Depends(_get_label_repo),
    client_repo: ClientRepository = Depends(get_client_repo),
    clock: Clock = Depends(get_clock),
) -> CreateClientPositionLabelUseCase:
    return CreateClientPositionLabelUseCase(
        label_repo=label_repo,
        client_repo=client_repo,
        clock=clock,
        signing=_signing_service(),
    )


def get_create_client_position_marker_set_use_case(
    label_repo=Depends(_get_label_repo),
    client_repo: ClientRepository = Depends(get_client_repo),
    clock: Clock = Depends(get_clock),
) -> CreateClientPositionMarkerSetUseCase:
    return CreateClientPositionMarkerSetUseCase(
        label_repo=label_repo,
        client_repo=client_repo,
        clock=clock,
        signing=_signing_service(),
    )


def get_list_client_position_labels_use_case(
    label_repo=Depends(_get_label_repo),
    client_repo: ClientRepository = Depends(get_client_repo),
) -> ListClientPositionLabelsUseCase:
    return ListClientPositionLabelsUseCase(label_repo=label_repo, client_repo=client_repo)


def get_get_client_position_label_use_case(
    label_repo=Depends(_get_label_repo),
    client_repo: ClientRepository = Depends(get_client_repo),
) -> GetClientPositionLabelUseCase:
    return GetClientPositionLabelUseCase(label_repo=label_repo, client_repo=client_repo)


def get_update_client_position_label_use_case(
    label_repo=Depends(_get_label_repo),
    client_repo: ClientRepository = Depends(get_client_repo),
    clock: Clock = Depends(get_clock),
) -> UpdateClientPositionLabelMetadataUseCase:
    return UpdateClientPositionLabelMetadataUseCase(
        label_repo=label_repo, client_repo=client_repo, clock=clock
    )


def get_invalidate_client_position_label_use_case(
    label_repo=Depends(_get_label_repo),
    client_repo: ClientRepository = Depends(get_client_repo),
    clock: Clock = Depends(get_clock),
) -> InvalidateClientPositionLabelUseCase:
    return InvalidateClientPositionLabelUseCase(
        label_repo=label_repo, client_repo=client_repo, clock=clock
    )


def get_render_client_position_label_use_case(
    label_repo=Depends(_get_label_repo),
    client_repo: ClientRepository = Depends(get_client_repo),
    clock: Clock = Depends(get_clock),
) -> RenderClientPositionLabelUseCase:
    container = get_app_container()
    return RenderClientPositionLabelUseCase(
        label_repo=label_repo,
        client_repo=client_repo,
        artifact_store=container.get_artifact_store(),
        renderer=PositioningLabelRenderer(),
        clock=clock,
    )


def get_download_client_position_label_use_case(
    label_repo=Depends(_get_label_repo),
    client_repo: ClientRepository = Depends(get_client_repo),
    clock: Clock = Depends(get_clock),
) -> DownloadClientPositionLabelUseCase:
    container = get_app_container()
    return DownloadClientPositionLabelUseCase(
        label_repo=label_repo,
        client_repo=client_repo,
        artifact_store=container.get_artifact_store(),
        renderer=PositioningLabelRenderer(),
        clock=clock,
    )


@router.get(
    "/{client_id}/position-labels",
    response_model=ClientPositionLabelListResponse,
)
def list_client_position_labels(
    client_id: str,
    status_filter: str | None = Query(default=None, alias="status"),
    search: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    principal: AccessPrincipal = Depends(get_access_principal),
    use_case: ListClientPositionLabelsUseCase = Depends(get_list_client_position_labels_use_case),
) -> ClientPositionLabelListResponse:
    try:
        _require_position_labels_enabled()
        offset = (page - 1) * page_size
        items, total = use_case.execute(
            ListClientPositionLabelsCommand(
                client_id=client_id,
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
    return ClientPositionLabelListResponse(
        items=[client_position_label_to_response(i) for i in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=compute_total_pages(total, page_size),
    )


@router.post(
    "/{client_id}/position-labels",
    response_model=ClientPositionLabelResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_client_position_label(
    client_id: str,
    body: CreateClientPositionLabelRequest,
    principal: AccessPrincipal = Depends(get_access_principal),
    use_case: CreateClientPositionLabelUseCase = Depends(
        get_create_client_position_label_use_case
    ),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> ClientPositionLabelResponse:
    try:
        _require_position_labels_enabled()
        label = use_case.execute(
            CreateClientPositionLabelCommand(
                client_id=client_id,
                name=body.name or "",
                description=body.description,
                principal=principal,
                idempotency_key=idempotency_key,
                pallet=body.pallet,
                side=body.side,
                level=body.level,
                marker_index=body.marker_index,
                marker_total=body.marker_total,
            )
        )
    except Exception as e:
        reraise_if_mapped(e)
        raise
    return client_position_label_to_response(label)


@router.post(
    "/{client_id}/position-labels/marker-set",
    response_model=ClientPositionLabelMarkerSetResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_client_position_marker_set(
    client_id: str,
    body: CreateClientPositionMarkerSetRequest,
    principal: AccessPrincipal = Depends(get_access_principal),
    use_case: CreateClientPositionMarkerSetUseCase = Depends(
        get_create_client_position_marker_set_use_case
    ),
) -> ClientPositionLabelMarkerSetResponse:
    try:
        _require_position_labels_enabled()
        labels = use_case.execute(
            CreateClientPositionMarkerSetCommand(
                client_id=client_id,
                pallet=body.pallet,
                side=body.side,
                level=body.level,
                marker_total=body.marker_total,
                description=body.description,
                principal=principal,
            )
        )
    except Exception as e:
        reraise_if_mapped(e)
        raise
    return ClientPositionLabelMarkerSetResponse(
        items=[client_position_label_to_response(label) for label in labels]
    )


@router.get(
    "/{client_id}/position-labels/{label_id}",
    response_model=ClientPositionLabelResponse,
)
def get_client_position_label(
    client_id: str,
    label_id: str,
    principal: AccessPrincipal = Depends(get_access_principal),
    use_case: GetClientPositionLabelUseCase = Depends(get_get_client_position_label_use_case),
) -> ClientPositionLabelResponse:
    try:
        _require_position_labels_enabled()
        label = use_case.execute(
            GetClientPositionLabelCommand(
                client_id=client_id, label_id=label_id, principal=principal
            )
        )
    except Exception as e:
        reraise_if_mapped(e)
        raise
    return client_position_label_to_response(label)


@router.patch(
    "/{client_id}/position-labels/{label_id}",
    response_model=ClientPositionLabelResponse,
)
def update_client_position_label(
    client_id: str,
    label_id: str,
    body: UpdateClientPositionLabelRequest,
    principal: AccessPrincipal = Depends(get_access_principal),
    use_case: UpdateClientPositionLabelMetadataUseCase = Depends(
        get_update_client_position_label_use_case
    ),
) -> ClientPositionLabelResponse:
    try:
        _require_position_labels_enabled()
        label = use_case.execute(
            UpdateClientPositionLabelMetadataCommand(
                client_id=client_id,
                label_id=label_id,
                principal=principal,
                name=body.name,
                description=body.description,
            )
        )
    except Exception as e:
        reraise_if_mapped(e)
        raise
    return client_position_label_to_response(label)


@router.post(
    "/{client_id}/position-labels/{label_id}/invalidate",
    response_model=ClientPositionLabelResponse,
)
def invalidate_client_position_label(
    client_id: str,
    label_id: str,
    body: InvalidateClientPositionLabelRequest | None = None,
    principal: AccessPrincipal = Depends(get_access_principal),
    use_case: InvalidateClientPositionLabelUseCase = Depends(
        get_invalidate_client_position_label_use_case
    ),
) -> ClientPositionLabelResponse:
    try:
        _require_position_labels_enabled()
        label = use_case.execute(
            InvalidateClientPositionLabelCommand(
                client_id=client_id,
                label_id=label_id,
                principal=principal,
                reason=(body.reason if body else None),
            )
        )
    except Exception as e:
        reraise_if_mapped(e)
        raise
    return client_position_label_to_response(label)


@router.post(
    "/{client_id}/position-labels/{label_id}/render",
    response_model=ClientPositionLabelArtifactResponse,
)
def render_client_position_label(
    client_id: str,
    label_id: str,
    body: RenderClientPositionLabelRequest | None = None,
    principal: AccessPrincipal = Depends(get_access_principal),
    use_case: RenderClientPositionLabelUseCase = Depends(
        get_render_client_position_label_use_case
    ),
) -> ClientPositionLabelArtifactResponse:
    req = body or RenderClientPositionLabelRequest()
    try:
        _require_position_labels_enabled()
        _require_position_label_render_enabled()
        artifact = use_case.execute(
            RenderClientPositionLabelCommand(
                client_id=client_id,
                label_id=label_id,
                principal=principal,
                format=req.format.upper(),  # type: ignore[arg-type]
                preset=req.preset,
            )
        )
    except Exception as e:
        reraise_if_mapped(e)
        raise
    return ClientPositionLabelArtifactResponse(
        id=artifact.id,
        label_id=artifact.label_id,
        format=artifact.format,
        preset=artifact.preset,
        content_type=artifact.content_type,
        file_size_bytes=artifact.file_size_bytes,
        artifact_hash=artifact.artifact_hash,
        created_at=artifact.created_at,
    )


def _download_response(
    *,
    client_id: str,
    label_id: str,
    fmt: str,
    preset: str,
    principal: AccessPrincipal,
    use_case: DownloadClientPositionLabelUseCase,
    disposition: str,
) -> FastAPIResponse:
    try:
        _require_position_labels_enabled()
        _require_position_label_render_enabled()
        result = use_case.execute(
            RenderClientPositionLabelCommand(
                client_id=client_id,
                label_id=label_id,
                principal=principal,
                format=fmt.upper(),  # type: ignore[arg-type]
                preset=preset,
            )
        )
    except Exception as e:
        reraise_if_mapped(e)
        raise
    headers = {
        "Content-Disposition": f'{disposition}; filename="{result.filename}"',
    }
    return Response(
        content=result.content,
        media_type=result.artifact.content_type,
        headers=headers,
    )


@router.get("/{client_id}/position-labels/{label_id}/preview")
def preview_client_position_label(
    client_id: str,
    label_id: str,
    format: str = Query(default="PNG"),
    preset: str = Query(default="MM_100x100"),
    principal: AccessPrincipal = Depends(get_access_principal),
    use_case: DownloadClientPositionLabelUseCase = Depends(
        get_download_client_position_label_use_case
    ),
) -> FastAPIResponse:
    return _download_response(
        client_id=client_id,
        label_id=label_id,
        fmt=format,
        preset=preset,
        principal=principal,
        use_case=use_case,
        disposition="inline",
    )


@router.get("/{client_id}/position-labels/{label_id}/download")
def download_client_position_label(
    client_id: str,
    label_id: str,
    format: str = Query(default="PDF"),
    preset: str = Query(default="MM_100x100"),
    principal: AccessPrincipal = Depends(get_access_principal),
    use_case: DownloadClientPositionLabelUseCase = Depends(
        get_download_client_position_label_use_case
    ),
) -> FastAPIResponse:
    return _download_response(
        client_id=client_id,
        label_id=label_id,
        fmt=format,
        preset=preset,
        principal=principal,
        use_case=use_case,
        disposition="attachment",
    )
