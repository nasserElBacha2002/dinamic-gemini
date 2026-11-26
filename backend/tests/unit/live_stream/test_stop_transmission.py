"""Stop transmission blocks publish until prepare clears the flag."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from src.application.dto.access_principal import AccessPrincipal
from src.application.ports.clock import Clock
from src.application.services.live_stream_credential_crypto import derive_channel_password
from src.application.services.live_stream_mediamtx_control import LiveStreamMediaMtxControl
from src.application.services.live_stream_status_service import LiveStreamStatusService
from src.application.services.mediamtx_auth_service import MediaMtxAuthService
from src.application.use_cases.live_stream.manage_live_stream import ManageLiveStreamUseCase
from src.domain.inventory.entities import (
    Inventory,
    InventoryProcessingMode,
    InventoryStatus,
)
from src.infrastructure.repositories.memory_inventory_repository import MemoryInventoryRepository
from src.infrastructure.repositories.memory_live_stream_repository import MemoryLiveStreamRepository


class _FixedClock(Clock):
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


def _use_case(
    *, inv_repo: MemoryInventoryRepository, live_repo: MemoryLiveStreamRepository, now: datetime
) -> ManageLiveStreamUseCase:
    return ManageLiveStreamUseCase(
        inventory_repo=inv_repo,
        aisle_repo=None,
        live_repo=live_repo,
        clock=_FixedClock(now),
        enabled=True,
        server_secret="unit-test-secret",
        rtmp_publish_base_url="rtmp://127.0.0.1:1935",
        hls_public_base_url="http://127.0.0.1:8888",
        status_service=LiveStreamStatusService(api_base_url=None),
        mediamtx_control=LiveStreamMediaMtxControl(api_base_url=None),
        public_link_base_url="http://localhost:5173",
        public_grant_default_ttl_hours=24,
    )


def test_stop_blocks_publish_until_prepare() -> None:
    live_repo = MemoryLiveStreamRepository()
    inv_repo = MemoryInventoryRepository()
    inv_id = str(uuid4())
    now = datetime.now(timezone.utc)
    inv_repo.save(
        Inventory(
            id=inv_id,
            name="Prueba18-09",
            client_id="c1",
            status=InventoryStatus.DRAFT,
            processing_mode=InventoryProcessingMode.PRODUCTION,
            created_at=now,
            updated_at=now,
        )
    )
    uc = _use_case(inv_repo=inv_repo, live_repo=live_repo, now=now)
    principal = AccessPrincipal(
        actor_id="admin", client_id="c1", roles=frozenset({"admin"}), is_platform=True
    )
    prepared = uc.prepare_channel(inventory_id=inv_id, aisle_code="P1", principal=principal)
    assert not prepared.status.publish_blocked

    stopped = uc.stop_transmission(inventory_id=inv_id, aisle_code="P1", principal=principal)
    assert stopped.status.publish_blocked

    auth = MediaMtxAuthService(repo=live_repo, server_secret="unit-test-secret", enabled=True)
    pub_pass = derive_channel_password(
        server_secret="unit-test-secret",
        mediamtx_path=prepared.channel.mediamtx_path,
        purpose="publish",
    )
    assert not auth.authorize(
        username=prepared.publish_username,
        password=pub_pass,
        path=prepared.channel.mediamtx_path,
        action="publish",
    ).allowed

    rehab = uc.prepare_channel(inventory_id=inv_id, aisle_code="P1", principal=principal)
    assert not rehab.status.publish_blocked
    assert auth.authorize(
        username=prepared.publish_username,
        password=pub_pass,
        path=prepared.channel.mediamtx_path,
        action="publish",
    ).allowed
