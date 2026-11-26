"""Anonymous public live viewer API — DIN-508 Phase 3."""

from __future__ import annotations

import urllib.error

from fastapi import APIRouter, Depends, HTTPException, Response

from src.api.deps.live_stream import (
    get_live_stream_hls_proxy_service,
    get_manage_live_stream_use_case,
)
from src.api.errors import reraise_if_mapped
from src.api.schemas.live_stream_schemas import PublicLivePlaybackResponse
from src.application.services.live_stream_hls_proxy import LiveStreamHlsProxyService
from src.application.use_cases.live_stream.manage_live_stream import ManageLiveStreamUseCase

router = APIRouter(prefix="/api/public/live", tags=["public-live"])


@router.get("/{token}", response_model=PublicLivePlaybackResponse)
def get_public_live_playback(
    token: str,
    response: Response,
    use_case: ManageLiveStreamUseCase = Depends(get_manage_live_stream_use_case),
) -> PublicLivePlaybackResponse:
    response.headers["Cache-Control"] = "no-store"
    try:
        ticket = use_case.resolve_public_playback(token=token)
    except Exception as exc:
        reraise_if_mapped(exc)
        raise
    return PublicLivePlaybackResponse(
        presence=ticket.presence,
        hls_playlist_url=ticket.hls_playlist_url,
        view_username=ticket.view_username,
        view_password=ticket.view_password,
        expires_at=ticket.expires_at,  # type: ignore[arg-type]
        publish_blocked=ticket.publish_blocked,
    )


@router.get("/{token}/hls/{resource_path:path}")
def proxy_public_hls(
    token: str,
    resource_path: str,
    use_case: ManageLiveStreamUseCase = Depends(get_manage_live_stream_use_case),
    proxy: LiveStreamHlsProxyService = Depends(get_live_stream_hls_proxy_service),
) -> Response:
    if not proxy.enabled:
        raise HTTPException(status_code=503, detail="HLS proxy is not configured")
    try:
        mediamtx_path, view_user, view_pass = use_case.resolve_public_hls_proxy_source(token=token)
    except Exception as exc:
        reraise_if_mapped(exc)
        raise
    from urllib.parse import quote

    tok = quote(token, safe="")
    proxy_prefix = f"/api/public/live/{tok}/hls"
    try:
        result = proxy.fetch(
            mediamtx_path=mediamtx_path,
            resource=resource_path,
            read_username=view_user,
            read_password=view_pass,
            proxy_entry_prefix=proxy_prefix,
        )
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise HTTPException(status_code=404, detail="HLS resource not found") from exc
        if exc.code in (401, 403):
            raise HTTPException(status_code=502, detail="HLS upstream unauthorized") from exc
        raise HTTPException(status_code=502, detail="HLS upstream error") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid HLS resource path") from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="HLS upstream unavailable") from exc
    return Response(
        content=result.body,
        media_type=result.content_type,
        headers={"Cache-Control": result.cache_control},
    )
