"""Anonymous public live viewer API — DIN-508 Phase 3."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from src.api.deps.live_stream import get_manage_live_stream_use_case
from src.api.errors import reraise_if_mapped
from src.api.schemas.live_stream_schemas import PublicLivePlaybackResponse
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