"""Live stream API dependency providers — DIN-508 Phase 3."""

from __future__ import annotations

from fastapi import Depends

from src.application.ports.clock import Clock
from src.application.ports.repositories import AisleRepository, InventoryRepository
from src.application.services.live_stream_mediamtx_control import LiveStreamMediaMtxControl
from src.application.services.live_stream_status_service import LiveStreamStatusService
from src.application.services.mediamtx_auth_service import MediaMtxAuthService
from src.application.use_cases.live_stream.manage_live_stream import ManageLiveStreamUseCase
from src.config import load_settings
from src.runtime.app_container import get_app_container
from src.runtime.v3_deps import get_aisle_repo, get_clock, get_inventory_repo


def get_manage_live_stream_use_case(
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    clock: Clock = Depends(get_clock),
) -> ManageLiveStreamUseCase:
    settings = load_settings()
    return ManageLiveStreamUseCase(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        live_repo=get_app_container().get_live_stream_repo(),
        clock=clock,
        enabled=bool(getattr(settings, "live_stream_enabled", False)),
        server_secret=(settings.auth_token_secret or "").strip(),
        rtmp_publish_base_url=getattr(settings, "live_stream_rtmp_publish_base_url", ""),
        hls_public_base_url=getattr(settings, "live_stream_hls_base_url", ""),
        status_service=LiveStreamStatusService(
            api_base_url=getattr(settings, "live_stream_mediamtx_api_url", None)
        ),
        mediamtx_control=LiveStreamMediaMtxControl(
            api_base_url=getattr(settings, "live_stream_mediamtx_api_url", None)
        ),
        public_link_base_url=getattr(settings, "live_stream_public_link_base_url", "")
        or "http://localhost:5173",
        public_grant_default_ttl_hours=int(
            getattr(settings, "live_stream_public_grant_default_ttl_hours", 24)
        ),
        fixed_publish_username=getattr(settings, "live_stream_fixed_publish_username", ""),
        fixed_publish_password=getattr(settings, "live_stream_fixed_publish_password", ""),
        fixed_read_username=getattr(settings, "live_stream_fixed_read_username", ""),
        fixed_read_password=getattr(settings, "live_stream_fixed_read_password", ""),
    )


def get_mediamtx_auth_service() -> MediaMtxAuthService:
    settings = load_settings()
    return MediaMtxAuthService(
        repo=get_app_container().get_live_stream_repo(),
        server_secret=(settings.auth_token_secret or "").strip(),
        enabled=bool(getattr(settings, "live_stream_enabled", False)),
    )
