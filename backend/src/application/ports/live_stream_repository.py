"""Ports for DIN-508 live stream persistence."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from src.domain.live_stream.entities import LiveChannelCredentials, LiveViewGrant


class LiveStreamRepository(ABC):
    @abstractmethod
    def upsert_channel_credentials(self, record: LiveChannelCredentials) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_channel_credentials(
        self, *, inventory_id: str, channel_slug: str
    ) -> LiveChannelCredentials | None:
        raise NotImplementedError

    @abstractmethod
    def get_channel_credentials_by_path(self, mediamtx_path: str) -> LiveChannelCredentials | None:
        raise NotImplementedError

    @abstractmethod
    def find_channel_credentials_by_publish_user(
        self, username: str
    ) -> LiveChannelCredentials | None:
        raise NotImplementedError

    @abstractmethod
    def find_channel_credentials_by_read_user(self, username: str) -> LiveChannelCredentials | None:
        raise NotImplementedError

    @abstractmethod
    def save_view_grant(self, grant: LiveViewGrant) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_view_grant_by_token_hash(self, token_hash: str) -> LiveViewGrant | None:
        raise NotImplementedError

    @abstractmethod
    def find_view_grant_by_view_user(self, username: str) -> LiveViewGrant | None:
        raise NotImplementedError

    @abstractmethod
    def list_view_grants_for_channel(
        self, *, inventory_id: str, channel_slug: str
    ) -> list[LiveViewGrant]:
        raise NotImplementedError

    @abstractmethod
    def revoke_view_grant(
        self, grant_id: str, *, inventory_id: str, revoked_at: datetime
    ) -> bool:
        raise NotImplementedError

    @abstractmethod
    def set_channel_publish_blocked(
        self,
        *,
        inventory_id: str,
        channel_slug: str,
        blocked_at: datetime | None,
        blocked_by_principal_id: str | None,
        updated_at: datetime,
    ) -> bool:
        """Update publish block flags; returns False if the channel row is missing."""
        raise NotImplementedError
