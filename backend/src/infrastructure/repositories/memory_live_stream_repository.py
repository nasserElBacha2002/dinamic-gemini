"""In-memory LiveStreamRepository — tests and memory backend."""

from __future__ import annotations

from datetime import datetime

from src.application.ports.live_stream_repository import LiveStreamRepository
from src.domain.live_stream.entities import LiveChannelCredentials, LiveViewGrant


class MemoryLiveStreamRepository(LiveStreamRepository):
    def __init__(self) -> None:
        self._channels: dict[tuple[str, str], LiveChannelCredentials] = {}
        self._channels_by_path: dict[str, LiveChannelCredentials] = {}
        self._channels_by_pub: dict[str, LiveChannelCredentials] = {}
        self._channels_by_read: dict[str, LiveChannelCredentials] = {}
        self._grants_by_hash: dict[str, LiveViewGrant] = {}
        self._grants_by_user: dict[str, LiveViewGrant] = {}
        self._grants_by_channel: dict[tuple[str, str], list[LiveViewGrant]] = {}

    def upsert_channel_credentials(self, record: LiveChannelCredentials) -> None:
        key = (record.inventory_id, record.channel_slug)
        self._channels[key] = record
        self._channels_by_path[record.mediamtx_path] = record
        self._channels_by_pub[record.publish_username] = record
        self._channels_by_read[record.read_username] = record

    def get_channel_credentials(
        self, *, inventory_id: str, channel_slug: str
    ) -> LiveChannelCredentials | None:
        return self._channels.get((inventory_id, channel_slug))

    def list_channel_credentials_for_inventory(
        self, inventory_id: str
    ) -> list[LiveChannelCredentials]:
        return [
            creds
            for (inv_id, _), creds in self._channels.items()
            if inv_id == inventory_id
        ]

    def get_channel_credentials_by_path(self, mediamtx_path: str) -> LiveChannelCredentials | None:
        return self._channels_by_path.get(mediamtx_path)

    def find_channel_credentials_by_publish_user(
        self, username: str
    ) -> LiveChannelCredentials | None:
        return self._channels_by_pub.get(username)

    def find_channel_credentials_by_read_user(self, username: str) -> LiveChannelCredentials | None:
        return self._channels_by_read.get(username)

    def save_view_grant(self, grant: LiveViewGrant) -> None:
        self._grants_by_hash[grant.token_hash] = grant
        self._grants_by_user[grant.view_username] = grant
        key = (grant.inventory_id, grant.channel_slug)
        self._grants_by_channel.setdefault(key, []).append(grant)

    def get_view_grant_by_token_hash(self, token_hash: str) -> LiveViewGrant | None:
        return self._grants_by_hash.get(token_hash)

    def find_view_grant_by_view_user(self, username: str) -> LiveViewGrant | None:
        return self._grants_by_user.get(username)

    def list_view_grants_for_channel(
        self, *, inventory_id: str, channel_slug: str
    ) -> list[LiveViewGrant]:
        return list(self._grants_by_channel.get((inventory_id, channel_slug), []))

    def revoke_view_grant(
        self, grant_id: str, *, inventory_id: str, revoked_at: datetime
    ) -> bool:
        for grant in self._grants_by_hash.values():
            if (
                grant.id == grant_id
                and grant.inventory_id == inventory_id
                and grant.revoked_at is None
            ):
                updated = LiveViewGrant(
                    id=grant.id,
                    inventory_id=grant.inventory_id,
                    channel_slug=grant.channel_slug,
                    mediamtx_path=grant.mediamtx_path,
                    token_hash=grant.token_hash,
                    view_username=grant.view_username,
                    view_password_hash=grant.view_password_hash,
                    created_by_principal_id=grant.created_by_principal_id,
                    created_at=grant.created_at,
                    expires_at=grant.expires_at,
                    revoked_at=revoked_at,
                )
                self._grants_by_hash[grant.token_hash] = updated
                self._grants_by_user[grant.view_username] = updated
                return True
        return False

    def set_channel_publish_blocked(
        self,
        *,
        inventory_id: str,
        channel_slug: str,
        blocked_at: datetime | None,
        blocked_by_principal_id: str | None,
        updated_at: datetime,
    ) -> bool:
        existing = self._channels.get((inventory_id, channel_slug))
        if existing is None:
            return False
        updated = LiveChannelCredentials(
            id=existing.id,
            inventory_id=existing.inventory_id,
            canonical_aisle_code=existing.canonical_aisle_code,
            channel_slug=existing.channel_slug,
            mediamtx_path=existing.mediamtx_path,
            publish_username=existing.publish_username,
            publish_password_hash=existing.publish_password_hash,
            read_username=existing.read_username,
            read_password_hash=existing.read_password_hash,
            created_by_principal_id=existing.created_by_principal_id,
            created_at=existing.created_at,
            updated_at=updated_at,
            publish_blocked_at=blocked_at,
            publish_blocked_by_principal_id=blocked_by_principal_id,
        )
        self.upsert_channel_credentials(updated)
        return True
