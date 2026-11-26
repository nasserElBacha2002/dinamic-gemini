"""SQL Server LiveStreamRepository — DIN-508 Phase 3."""

from __future__ import annotations

from datetime import datetime, timezone

from src.application.errors import RepositoryRowMappingError
from src.application.ports.live_stream_repository import LiveStreamRepository
from src.database.sqlserver import SqlServerClient
from src.domain.live_stream.entities import LiveChannelCredentials, LiveViewGrant
from src.infrastructure.database.sql_transaction import sql_repository_cursor


def _ensure_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt
    return dt.replace(tzinfo=timezone.utc)


def _channel_from_row(row: object) -> LiveChannelCredentials:
    created = _ensure_utc(getattr(row, "created_at", None))
    updated = _ensure_utc(getattr(row, "updated_at", None))
    if created is None or updated is None:
        raise RepositoryRowMappingError("aisle_live_channel_credentials missing timestamps")
    blocked_at = _ensure_utc(getattr(row, "publish_blocked_at", None))
    blocked_by = getattr(row, "publish_blocked_by_principal_id", None)
    return LiveChannelCredentials(
        id=str(getattr(row, "id")),
        inventory_id=str(getattr(row, "inventory_id")),
        canonical_aisle_code=str(getattr(row, "canonical_aisle_code")),
        channel_slug=str(getattr(row, "channel_slug")),
        mediamtx_path=str(getattr(row, "mediamtx_path")),
        publish_username=str(getattr(row, "publish_username")),
        publish_password_hash=str(getattr(row, "publish_password_hash")),
        read_username=str(getattr(row, "read_username")),
        read_password_hash=str(getattr(row, "read_password_hash")),
        created_by_principal_id=str(getattr(row, "created_by_principal_id")),
        created_at=created,
        updated_at=updated,
        publish_blocked_at=blocked_at,
        publish_blocked_by_principal_id=(
            str(blocked_by) if blocked_by is not None and str(blocked_by).strip() else None
        ),
    )


def _grant_from_row(row: object) -> LiveViewGrant:
    created = _ensure_utc(getattr(row, "created_at", None))
    expires = _ensure_utc(getattr(row, "expires_at", None))
    revoked = _ensure_utc(getattr(row, "revoked_at", None))
    if created is None or expires is None:
        raise RepositoryRowMappingError("aisle_live_view_grants missing timestamps")
    return LiveViewGrant(
        id=str(getattr(row, "id")),
        inventory_id=str(getattr(row, "inventory_id")),
        channel_slug=str(getattr(row, "channel_slug")),
        mediamtx_path=str(getattr(row, "mediamtx_path")),
        token_hash=str(getattr(row, "token_hash")),
        view_username=str(getattr(row, "view_username")),
        view_password_hash=str(getattr(row, "view_password_hash")),
        created_by_principal_id=str(getattr(row, "created_by_principal_id")),
        created_at=created,
        expires_at=expires,
        revoked_at=revoked,
    )


class SqlLiveStreamRepository(LiveStreamRepository):
    def __init__(self, client: SqlServerClient) -> None:
        self._client = client

    def upsert_channel_credentials(self, record: LiveChannelCredentials) -> None:
        with sql_repository_cursor(self._client) as cur:
            cur.execute(
                """
                SELECT id FROM aisle_live_channel_credentials
                WHERE inventory_id = ? AND channel_slug = ?
                """,
                (record.inventory_id, record.channel_slug),
            )
            row = cur.fetchone()
            if row:
                cur.execute(
                    """
                    UPDATE aisle_live_channel_credentials
                    SET canonical_aisle_code = ?, mediamtx_path = ?,
                        publish_username = ?, publish_password_hash = ?,
                        read_username = ?, read_password_hash = ?,
                        created_by_principal_id = ?, updated_at = ?,
                        publish_blocked_at = ?, publish_blocked_by_principal_id = ?
                    WHERE inventory_id = ? AND channel_slug = ?
                    """,
                    (
                        record.canonical_aisle_code,
                        record.mediamtx_path,
                        record.publish_username,
                        record.publish_password_hash,
                        record.read_username,
                        record.read_password_hash,
                        record.created_by_principal_id,
                        record.updated_at,
                        record.publish_blocked_at,
                        record.publish_blocked_by_principal_id,
                        record.inventory_id,
                        record.channel_slug,
                    ),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO aisle_live_channel_credentials (
                        id, inventory_id, canonical_aisle_code, channel_slug, mediamtx_path,
                        publish_username, publish_password_hash, read_username, read_password_hash,
                        created_by_principal_id, created_at, updated_at,
                        publish_blocked_at, publish_blocked_by_principal_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.id,
                        record.inventory_id,
                        record.canonical_aisle_code,
                        record.channel_slug,
                        record.mediamtx_path,
                        record.publish_username,
                        record.publish_password_hash,
                        record.read_username,
                        record.read_password_hash,
                        record.created_by_principal_id,
                        record.created_at,
                        record.updated_at,
                        record.publish_blocked_at,
                        record.publish_blocked_by_principal_id,
                    ),
                )

    def get_channel_credentials(
        self, *, inventory_id: str, channel_slug: str
    ) -> LiveChannelCredentials | None:
        with sql_repository_cursor(self._client) as cur:
            cur.execute(
                """
                SELECT id, inventory_id, canonical_aisle_code, channel_slug, mediamtx_path,
                       publish_username, publish_password_hash, read_username, read_password_hash,
                       created_by_principal_id, created_at, updated_at,
                       publish_blocked_at, publish_blocked_by_principal_id
                FROM aisle_live_channel_credentials
                WHERE inventory_id = ? AND channel_slug = ?
                """,
                (inventory_id, channel_slug),
            )
            row = cur.fetchone()
        return _channel_from_row(row) if row else None

    def get_channel_credentials_by_path(self, mediamtx_path: str) -> LiveChannelCredentials | None:
        with sql_repository_cursor(self._client) as cur:
            cur.execute(
                """
                SELECT id, inventory_id, canonical_aisle_code, channel_slug, mediamtx_path,
                       publish_username, publish_password_hash, read_username, read_password_hash,
                       created_by_principal_id, created_at, updated_at,
                       publish_blocked_at, publish_blocked_by_principal_id
                FROM aisle_live_channel_credentials WHERE mediamtx_path = ?
                """,
                (mediamtx_path,),
            )
            row = cur.fetchone()
        return _channel_from_row(row) if row else None

    def find_channel_credentials_by_publish_user(
        self, username: str
    ) -> LiveChannelCredentials | None:
        with sql_repository_cursor(self._client) as cur:
            cur.execute(
                """
                SELECT id, inventory_id, canonical_aisle_code, channel_slug, mediamtx_path,
                       publish_username, publish_password_hash, read_username, read_password_hash,
                       created_by_principal_id, created_at, updated_at,
                       publish_blocked_at, publish_blocked_by_principal_id
                FROM aisle_live_channel_credentials WHERE publish_username = ?
                """,
                (username,),
            )
            row = cur.fetchone()
        return _channel_from_row(row) if row else None

    def find_channel_credentials_by_read_user(self, username: str) -> LiveChannelCredentials | None:
        with sql_repository_cursor(self._client) as cur:
            cur.execute(
                """
                SELECT id, inventory_id, canonical_aisle_code, channel_slug, mediamtx_path,
                       publish_username, publish_password_hash, read_username, read_password_hash,
                       created_by_principal_id, created_at, updated_at,
                       publish_blocked_at, publish_blocked_by_principal_id
                FROM aisle_live_channel_credentials WHERE read_username = ?
                """,
                (username,),
            )
            row = cur.fetchone()
        return _channel_from_row(row) if row else None

    def save_view_grant(self, grant: LiveViewGrant) -> None:
        with sql_repository_cursor(self._client) as cur:
            cur.execute(
                """
                INSERT INTO aisle_live_view_grants (
                    id, inventory_id, channel_slug, mediamtx_path, token_hash,
                    view_username, view_password_hash, created_by_principal_id,
                    created_at, expires_at, revoked_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    grant.id,
                    grant.inventory_id,
                    grant.channel_slug,
                    grant.mediamtx_path,
                    grant.token_hash,
                    grant.view_username,
                    grant.view_password_hash,
                    grant.created_by_principal_id,
                    grant.created_at,
                    grant.expires_at,
                    grant.revoked_at,
                ),
            )

    def get_view_grant_by_token_hash(self, token_hash: str) -> LiveViewGrant | None:
        with sql_repository_cursor(self._client) as cur:
            cur.execute(
                """
                SELECT id, inventory_id, channel_slug, mediamtx_path, token_hash,
                       view_username, view_password_hash, created_by_principal_id,
                       created_at, expires_at, revoked_at
                FROM aisle_live_view_grants WHERE token_hash = ?
                """,
                (token_hash,),
            )
            row = cur.fetchone()
        return _grant_from_row(row) if row else None

    def find_view_grant_by_view_user(self, username: str) -> LiveViewGrant | None:
        with sql_repository_cursor(self._client) as cur:
            cur.execute(
                """
                SELECT id, inventory_id, channel_slug, mediamtx_path, token_hash,
                       view_username, view_password_hash, created_by_principal_id,
                       created_at, expires_at, revoked_at
                FROM aisle_live_view_grants WHERE view_username = ?
                """,
                (username,),
            )
            row = cur.fetchone()
        return _grant_from_row(row) if row else None

    def list_view_grants_for_channel(
        self, *, inventory_id: str, channel_slug: str
    ) -> list[LiveViewGrant]:
        with sql_repository_cursor(self._client) as cur:
            cur.execute(
                """
                SELECT id, inventory_id, channel_slug, mediamtx_path, token_hash,
                       view_username, view_password_hash, created_by_principal_id,
                       created_at, expires_at, revoked_at
                FROM aisle_live_view_grants
                WHERE inventory_id = ? AND channel_slug = ?
                ORDER BY created_at DESC
                """,
                (inventory_id, channel_slug),
            )
            rows = cur.fetchall()
        return [_grant_from_row(r) for r in rows]

    def revoke_view_grant(
        self, grant_id: str, *, inventory_id: str, revoked_at: datetime
    ) -> bool:
        with sql_repository_cursor(self._client) as cur:
            cur.execute(
                """
                UPDATE aisle_live_view_grants
                SET revoked_at = ?
                WHERE id = ? AND inventory_id = ? AND revoked_at IS NULL
                """,
                (revoked_at, grant_id, inventory_id),
            )
            return cur.rowcount > 0

    def set_channel_publish_blocked(
        self,
        *,
        inventory_id: str,
        channel_slug: str,
        blocked_at: datetime | None,
        blocked_by_principal_id: str | None,
        updated_at: datetime,
    ) -> bool:
        with sql_repository_cursor(self._client) as cur:
            cur.execute(
                """
                UPDATE aisle_live_channel_credentials
                SET publish_blocked_at = ?, publish_blocked_by_principal_id = ?, updated_at = ?
                WHERE inventory_id = ? AND channel_slug = ?
                """,
                (
                    blocked_at,
                    blocked_by_principal_id,
                    updated_at,
                    inventory_id,
                    channel_slug,
                ),
            )
            return cur.rowcount > 0
