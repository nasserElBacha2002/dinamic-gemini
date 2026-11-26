"""Viewer HLS playlist URL builds proxy path when internal MediaMTX HLS is configured."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from src.application.dto.access_principal import AccessPrincipal
from src.application.ports.clock import Clock
from src.application.services.live_stream_mediamtx_control import LiveStreamMediaMtxControl
from src.application.services.live_stream_status_service import LiveStreamStatusService
from src.application.use_cases.live_stream.manage_live_stream import ManageLiveStreamUseCase
from src.domain.inventory.entities import (
    Inventory,
    InventoryProcessingMode,
    InventoryStatus,
)
from src.infrastructure.repositories.memory_inventory_repository import MemoryInventoryRepository
from src.infrastructure.repositories.memory_live_stream_repository import MemoryLiveStreamRepository


class _FixedClock(Clock):
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


def test_prepare_returns_api_proxy_playlist_when_internal_hls_configured() -> None:
    inv_id = str(uuid4())
    inv_repo = MemoryInventoryRepository()
    inv_repo.save(
        Inventory(
            id=inv_id,
            name="inv",
            client_id="c1",
            status=InventoryStatus.DRAFT,
            processing_mode=InventoryProcessingMode.PRODUCTION,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
    )
    uc = ManageLiveStreamUseCase(
        inventory_repo=inv_repo,
        aisle_repo=None,
        live_repo=MemoryLiveStreamRepository(),
        clock=_FixedClock(),
        enabled=True,
        server_secret="secret",
        rtmp_publish_base_url="rtmp://x/live",
        hls_public_base_url="https://api.example/live-hls",
        status_service=LiveStreamStatusService(api_base_url=None),
        mediamtx_control=LiveStreamMediaMtxControl(api_base_url=None),
        public_link_base_url="http://localhost:5173",
        public_grant_default_ttl_hours=24,
        mediamtx_hls_internal_url="http://mediamtx:8888",
    )
    principal = AccessPrincipal(
        actor_id="u1", client_id="c1", roles=frozenset({"admin"}), is_platform=True
    )
    result = uc.prepare_channel(inventory_id=inv_id, aisle_code="P1", principal=principal)
    assert "/live-stream/hls/" in result.hls_playlist_url
    assert result.hls_playlist_url.endswith("/index.m3u8")
    assert "live-hls" not in result.hls_playlist_url
