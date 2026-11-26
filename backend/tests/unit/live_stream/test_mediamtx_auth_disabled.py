"""MediaMTX auth rejects all when live stream disabled."""

from __future__ import annotations

from src.application.services.mediamtx_auth_service import MediaMtxAuthService
from src.infrastructure.repositories.memory_live_stream_repository import MemoryLiveStreamRepository


def test_disabled_denies_all() -> None:
    svc = MediaMtxAuthService(repo=MemoryLiveStreamRepository(), server_secret="s", enabled=False)
    decision = svc.authorize(
        username="any",
        password="any",
        path="live/x/y",
        action="read",
    )
    assert not decision.allowed