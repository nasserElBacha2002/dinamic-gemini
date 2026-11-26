"""v3 live stream routes — DIN-508 Phase 3."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from src.api.deps.live_stream import get_manage_live_stream_use_case
from src.api.deps.security import require_inventory_client_scope
from src.api.errors import reraise_if_mapped
from src.api.schemas.live_stream_schemas import (
    CreatePublicLiveGrantRequest,
    LiveStreamPlaybackResponse,
    LiveStreamPrepareRequest,
    LiveStreamPrepareResponse,
    LiveStreamStatusResponse,
    LiveStreamStopRequest,
    LiveStreamStopResponse,
    PublicLiveGrantListItem,
    PublicLiveGrantResponse,
)
from src.application.dto.access_principal import AccessPrincipal
from src.application.use_cases.live_stream.manage_live_stream import ManageLiveStreamUseCase

router = APIRouter(prefix="/{inventory_id}/live-stream")


def _status_to_response(status) -> LiveStreamStatusResponse:
    return LiveStreamStatusResponse(
        presence=status.presence,
        publisher_ready=status.publisher_ready,
        bytes_received=status.bytes_received,
        publish_blocked=status.publish_blocked,
    )


@router.post("/prepare", response_model=LiveStreamPrepareResponse, status_code=status.HTTP_200_OK)
def prepare_live_stream(
    inventory_id: str,
    body: LiveStreamPrepareRequest,
    principal: AccessPrincipal = Depends(require_inventory_client_scope),
    use_case: ManageLiveStreamUseCase = Depends(get_manage_live_stream_use_case),
) -> LiveStreamPrepareResponse:
    try:
        result = use_case.prepare_channel(
            inventory_id=inventory_id,
            aisle_code=body.aisle_code,
            principal=principal,
        )
    except Exception as exc:
        reraise_if_mapped(exc)
        raise
    ch = result.channel
    return LiveStreamPrepareResponse(
        inventory_id=ch.inventory_id,
        aisle_code=ch.aisle_code_input,
        canonical_aisle_code=ch.canonical_aisle_code,
        channel_slug=ch.channel_slug,
        mediamtx_path=ch.mediamtx_path,
        aisle_id=ch.aisle_id,
        rtmp_publish_url=result.rtmp_publish_url,
        publish_username=result.publish_username,
        publish_password=result.publish_password,
        read_username=result.read_username,
        read_password=result.read_password,
        hls_playlist_url=result.hls_playlist_url,
        status=_status_to_response(result.status),
    )


@router.post("/stop", response_model=LiveStreamStopResponse, status_code=status.HTTP_200_OK)
def stop_live_stream(
    inventory_id: str,
    body: LiveStreamStopRequest,
    principal: AccessPrincipal = Depends(require_inventory_client_scope),
    use_case: ManageLiveStreamUseCase = Depends(get_manage_live_stream_use_case),
) -> LiveStreamStopResponse:
    try:
        result = use_case.stop_transmission(
            inventory_id=inventory_id,
            aisle_code=body.aisle_code,
            principal=principal,
        )
    except Exception as exc:
        reraise_if_mapped(exc)
        raise
    ch = result.channel
    return LiveStreamStopResponse(
        aisle_code=ch.aisle_code_input,
        canonical_aisle_code=ch.canonical_aisle_code,
        mediamtx_path=ch.mediamtx_path,
        publisher_kicked=result.publisher_kicked,
        status=_status_to_response(result.status),
    )


@router.get("/status", response_model=LiveStreamStatusResponse)
def get_live_stream_status(
    inventory_id: str,
    aisle_code: str,
    principal: AccessPrincipal = Depends(require_inventory_client_scope),
    use_case: ManageLiveStreamUseCase = Depends(get_manage_live_stream_use_case),
) -> LiveStreamStatusResponse:
    try:
        _resolved, status = use_case.get_status(
            inventory_id=inventory_id,
            aisle_code=aisle_code,
            principal=principal,
        )
    except Exception as exc:
        reraise_if_mapped(exc)
        raise
    return _status_to_response(status)


@router.get("/playback", response_model=LiveStreamPlaybackResponse)
def get_live_stream_playback(
    inventory_id: str,
    aisle_code: str,
    principal: AccessPrincipal = Depends(require_inventory_client_scope),
    use_case: ManageLiveStreamUseCase = Depends(get_manage_live_stream_use_case),
) -> LiveStreamPlaybackResponse:
    try:
        resolved, hls, user, password, status = use_case.get_internal_playback(
            inventory_id=inventory_id,
            aisle_code=aisle_code,
            principal=principal,
        )
    except Exception as exc:
        reraise_if_mapped(exc)
        raise
    return LiveStreamPlaybackResponse(
        mediamtx_path=resolved.mediamtx_path,
        hls_playlist_url=hls,
        read_username=user,
        read_password=password,
        status=_status_to_response(status),
    )


@router.post(
    "/public-grants",
    response_model=PublicLiveGrantResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_public_live_grant(
    inventory_id: str,
    body: CreatePublicLiveGrantRequest,
    principal: AccessPrincipal = Depends(require_inventory_client_scope),
    use_case: ManageLiveStreamUseCase = Depends(get_manage_live_stream_use_case),
) -> PublicLiveGrantResponse:
    try:
        created = use_case.create_public_grant(
            inventory_id=inventory_id,
            aisle_code=body.aisle_code,
            principal=principal,
            ttl_hours=body.ttl_hours,
        )
    except Exception as exc:
        reraise_if_mapped(exc)
        raise
    return PublicLiveGrantResponse(
        grant_id=created.grant_id,
        public_url=created.public_url,
        expires_at=created.expires_at,  # type: ignore[arg-type]
        view_username=created.view_username,
        view_password=created.view_password,
    )


@router.get("/public-grants", response_model=list[PublicLiveGrantListItem])
def list_public_live_grants(
    inventory_id: str,
    aisle_code: str,
    principal: AccessPrincipal = Depends(require_inventory_client_scope),
    use_case: ManageLiveStreamUseCase = Depends(get_manage_live_stream_use_case),
) -> list[PublicLiveGrantListItem]:
    try:
        grants = use_case.list_public_grants(
            inventory_id=inventory_id,
            aisle_code=aisle_code,
            principal=principal,
        )
    except Exception as exc:
        reraise_if_mapped(exc)
        raise
    return [
        PublicLiveGrantListItem(
            grant_id=g.grant_id,
            created_at=g.created_at,  # type: ignore[arg-type]
            expires_at=g.expires_at,  # type: ignore[arg-type]
            revoked_at=g.revoked_at,  # type: ignore[arg-type]
        )
        for g in grants
    ]


@router.delete("/public-grants/{grant_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_public_live_grant(
    inventory_id: str,
    grant_id: str,
    principal: AccessPrincipal = Depends(require_inventory_client_scope),
    use_case: ManageLiveStreamUseCase = Depends(get_manage_live_stream_use_case),
) -> None:
    try:
        use_case.revoke_public_grant(
            inventory_id=inventory_id,
            grant_id=grant_id,
            principal=principal,
        )
    except Exception as exc:
        reraise_if_mapped(exc)
        raise
