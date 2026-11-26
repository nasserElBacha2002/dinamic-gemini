"""Validate MediaMTX authHTTP callbacks against persisted credentials."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from src.application.ports.live_stream_repository import LiveStreamRepository
from src.application.services.live_stream_credential_crypto import (
    derive_channel_password,
    derive_public_grant_password,
    passwords_equal,
    verify_live_stream_secret,
)

logger = logging.getLogger(__name__)

_PUBLISH_ACTIONS = frozenset({"publish"})
_READ_ACTIONS = frozenset({"read", "playback"})


@dataclass(frozen=True)
class MediaMtxAuthDecision:
    allowed: bool
    expire_at: datetime | None = None


class MediaMtxAuthService:
    def __init__(
        self,
        *,
        repo: LiveStreamRepository,
        server_secret: str,
        enabled: bool,
    ) -> None:
        self._repo = repo
        self._server_secret = server_secret
        self._enabled = enabled

    def authorize(
        self,
        *,
        username: str,
        password: str,
        path: str,
        action: str,
        now: datetime | None = None,
    ) -> MediaMtxAuthDecision:
        if not self._enabled:
            logger.info("event=mediamtx_auth_denied reason=live_stream_disabled")
            return MediaMtxAuthDecision(allowed=False)

        user = (username or "").strip()
        pwd = password or ""
        mtx_path = self._normalize_path(path)
        act = (action or "").strip().lower()
        if not user or not pwd or not mtx_path or not act:
            return MediaMtxAuthDecision(allowed=False)

        if act in _PUBLISH_ACTIONS:
            channel = self._repo.find_channel_credentials_by_publish_user(user)
            if channel is not None:
                if channel.mediamtx_path != mtx_path:
                    return MediaMtxAuthDecision(allowed=False)
                expected = derive_channel_password(
                    server_secret=self._server_secret,
                    mediamtx_path=channel.mediamtx_path,
                    purpose="publish",
                )
                if channel.publish_blocked_at is not None:
                    logger.info(
                        "event=mediamtx_auth_denied reason=publish_blocked path=%s user=%s",
                        mtx_path,
                        user,
                    )
                    return MediaMtxAuthDecision(allowed=False)
                if passwords_equal(pwd, expected) or verify_live_stream_secret(
                    pwd, channel.publish_password_hash
                ):
                    return MediaMtxAuthDecision(allowed=True)
                logger.info(
                    "event=mediamtx_auth_denied reason=publish_credential_mismatch path=%s user=%s",
                    mtx_path,
                    user,
                )
                return MediaMtxAuthDecision(allowed=False)

        channel_read = self._repo.find_channel_credentials_by_read_user(user)
        if channel_read is not None:
            if act not in _READ_ACTIONS:
                return MediaMtxAuthDecision(allowed=False)
            if channel_read.mediamtx_path != mtx_path:
                return MediaMtxAuthDecision(allowed=False)
            expected = derive_channel_password(
                server_secret=self._server_secret,
                mediamtx_path=channel_read.mediamtx_path,
                purpose="read",
            )
            if passwords_equal(pwd, expected) or verify_live_stream_secret(
                pwd, channel_read.read_password_hash
            ):
                return MediaMtxAuthDecision(allowed=True)
            return MediaMtxAuthDecision(allowed=False)

        grant = self._repo.find_view_grant_by_view_user(user)
        if grant is not None:
            if act not in _READ_ACTIONS:
                return MediaMtxAuthDecision(allowed=False)
            if grant.mediamtx_path != mtx_path:
                return MediaMtxAuthDecision(allowed=False)
            instant = now or datetime.now(timezone.utc)
            if grant.revoked_at is not None or grant.expires_at <= instant:
                return MediaMtxAuthDecision(allowed=False)
            expected = derive_public_grant_password(
                server_secret=self._server_secret, grant_id=grant.id
            )
            if passwords_equal(pwd, expected):
                return MediaMtxAuthDecision(allowed=True, expire_at=grant.expires_at)
            return MediaMtxAuthDecision(allowed=False)

        logger.info("event=mediamtx_auth_denied reason=unknown_user action=%s", act)
        return MediaMtxAuthDecision(allowed=False)

    @staticmethod
    def _normalize_path(path: str) -> str:
        return (path or "").strip().lstrip("/")
