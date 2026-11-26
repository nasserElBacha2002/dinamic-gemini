"""Read-only channel recovery must not clear publish block."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from src.application.dto.access_principal import AccessPrincipal
from src.application.ports.clock import Clock
from src.application.services.live_stream_mediamtx_control import LiveStreamMediaMtxControl
from src.application.services.live_stream_status_service import LiveStreamStatusService
from src.application.use_cases.live_stream.manage_live_stream import ManageLiveStreamUseCase
from src.domain.inventory.entities import Inventory, InventoryProcessingMode, InventoryStatus
from src.infrastructure.repositories.memory_inventory_repository import MemoryInventoryRepository
from src.infrastructure.repositories.memory_live_stream_repository import MemoryLiveStreamRepository


class _FixedClock(Clock):
    def __init__(self, instant: datetime) -> None:
        self._instant = instant

    def now(self) -> datetime:
        return self._instant


def test_get_prepared_channel_preserves_publish_block() -> None:
    live_repo = MemoryLiveStreamRepository()
    inv_repo = MemoryInventoryRepository()
    inv_id = str(uuid4())
    now = datetime.now(timezone.utc)
    inv_repo.save(
        Inventory(
            id=inv_id,
            name="t",
            client_id="c1",
            status=InventoryStatus.DRAFT,
            processing_mode=InventoryProcessingMode.PRODUCTION,
            created_at=now,
            updated_at=now,
        )
    )
    uc = ManageLiveStreamUseCase(
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
    principal = AccessPrincipal(
        actor_id="admin", client_id="c1", roles=frozenset({"admin"}), is_platform=True
    )
    prepared = uc.prepare_channel(inventory_id=inv_id, aisle_code="P1", principal=principal)
    blocked_at = now
    live_repo.set_channel_publish_blocked(
        inventory_id=inv_id,
        channel_slug=prepared.channel.channel_slug,
        blocked_at=blocked_at,
        blocked_by_principal_id="admin",
        updated_at=blocked_at,
    )
    creds = live_repo.get_channel_credentials(
        inventory_id=inv_id, channel_slug=prepared.channel.channel_slug
    )
    assert creds is not None
    assert creds.publish_blocked_at is not None

    recovered = uc.get_prepared_channel(inventory_id=inv_id, aisle_code="P1", principal=principal)
    assert recovered.status.publish_blocked is True
    after = live_repo.get_channel_credentials(
        inventory_id=inv_id, channel_slug=prepared.channel.channel_slug
    )
    assert after is not None
    assert after.publish_blocked_at is not None