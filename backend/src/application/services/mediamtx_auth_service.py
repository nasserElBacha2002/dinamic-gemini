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
from src.domain.live_stream.entities import LiveChannelCredentials

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
        fixed_publish_username: str = "",
        fixed_publish_password: str = "",
    ) -> None:
        self._repo = repo
        self._server_secret = server_secret
        self._enabled = enabled
        self._fixed_publish_user = (fixed_publish_username or "").strip()
        self._fixed_publish_password = fixed_publish_password or ""

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
        if not pwd or not act:
            logger.info(
                "event=mediamtx_auth_denied reason=missing_fields path=%s user=%s action=%s",
                mtx_path,
                user or "(empty)",
                act,
            )
            return MediaMtxAuthDecision(allowed=False)

        if act in _PUBLISH_ACTIONS:
            channel = self._repo.find_channel_credentials_by_publish_user(user) if user else None
            if channel is None and mtx_path:
                channel = self._repo.get_channel_credentials_by_path(mtx_path)
            if channel is not None and self._allow_publish(channel=channel, pwd=pwd, user=user, mtx_path=mtx_path):
                return MediaMtxAuthDecision(allowed=True)
            if channel is not None:
                logger.info(
                    "event=mediamtx_auth_denied reason=publish_credential_mismatch path=%s user=%s",
                    mtx_path,
                    user,
                )
                return MediaMtxAuthDecision(allowed=False)
            if (
                self._fixed_publish_user
                and self._fixed_publish_password
                and user
                and passwords_equal(user, self._fixed_publish_user)
                and passwords_equal(pwd, self._fixed_publish_password)
                and mtx_path
            ):
                by_path = self._repo.get_channel_credentials_by_path(mtx_path)
                if by_path is not None and by_path.publish_blocked_at is None:
                    return MediaMtxAuthDecision(allowed=True)
            logger.info(
                "event=mediamtx_auth_denied reason=publish_rejected path=%s user=%s",
                mtx_path,
                user or "(empty)",
            )
            return MediaMtxAuthDecision(allowed=False)

        if act not in _READ_ACTIONS:
            logger.info(
                "event=mediamtx_auth_denied reason=unknown_user action=%s path=%s user=%s",
                act,
                mtx_path,
                user,
            )
            return MediaMtxAuthDecision(allowed=False)

        if not user:
            logger.info(
                "event=mediamtx_auth_denied reason=missing_user path=%s action=%s",
                mtx_path,
                act,
            )
            return MediaMtxAuthDecision(allowed=False)

        channel_read = self._repo.find_channel_credentials_by_read_user(user)
        if channel_read is not None:
            if act not in _READ_ACTIONS:
                return MediaMtxAuthDecision(allowed=False)
            if mtx_path and not self._paths_compatible(mtx_path, channel_read.mediamtx_path):
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
            if mtx_path and not self._paths_compatible(mtx_path, grant.mediamtx_path):
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

        logger.info(
            "event=mediamtx_auth_denied reason=unknown_user action=%s path=%s user=%s",
            act,
            mtx_path,
            user,
        )
        return MediaMtxAuthDecision(allowed=False)

    def _allow_publish(
        self,
        *,
        channel: LiveChannelCredentials,
        pwd: str,
        user: str,
        mtx_path: str,
    ) -> bool:
        if mtx_path and not self._paths_compatible(mtx_path, channel.mediamtx_path):
            logger.info(
                "event=mediamtx_auth_denied reason=path_mismatch path=%s expected=%s user=%s",
                mtx_path,
                channel.mediamtx_path,
                user,
            )
            return False
        if channel.publish_blocked_at is not None:
            logger.info(
                "event=mediamtx_auth_denied reason=publish_blocked path=%s user=%s",
                mtx_path,
                user,
            )
            return False
        if (
            self._fixed_publish_user
            and self._fixed_publish_password
            and passwords_equal(pwd, self._fixed_publish_password)
            and (not user or passwords_equal(user, self._fixed_publish_user))
        ):
            return True
        expected = derive_channel_password(
            server_secret=self._server_secret,
            mediamtx_path=channel.mediamtx_path,
            purpose="publish",
        )
        return passwords_equal(pwd, expected) or verify_live_stream_secret(
            pwd, channel.publish_password_hash
        )

    @staticmethod
    def _normalize_path(path: str) -> str:
        return (path or "").strip().lstrip("/")

    @staticmethod
    def _paths_compatible(requested: str, channel_path: str) -> bool:
        """Match exact path or DJI-style stream key suffix / empty path on RTMP connect."""
        req = MediaMtxAuthService._normalize_path(requested)
        ch = MediaMtxAuthService._normalize_path(channel_path)
        if not req:
            return True
        if req == ch:
            return True
        if ch.endswith(f"/{req}") or ch.split("/")[-1] == req:
            return True
        return False
