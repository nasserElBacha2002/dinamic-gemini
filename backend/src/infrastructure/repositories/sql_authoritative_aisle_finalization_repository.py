"""SQL Server repository for authoritative aisle finalization (Phase 6)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone

from src.database.sqlserver import SqlServerClient
from src.domain.authoritative_aisle_finalization.entities import (
    AuthoritativeAisleExcludedAsset,
    AuthoritativeAisleFinalization,
    AuthoritativeAisleFinalizationItem,
)
from src.infrastructure.repositories.db_row_text import normalize_db_str, optional_nonempty_db_str

_FIN_COLS = (
    "id, inventory_id, aisle_id, capture_session_id, finalization_version, status, "
    "total_assets, applied_assets, excluded_assets, position_count, expected_asset_count, "
    "content_hash, confirmed_by, confirmed_at, completed_at, is_current, row_version, "
    "created_at, updated_at"
)


def _ensure_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt
    return dt.replace(tzinfo=timezone.utc)


def _fin_from_row(row) -> AuthoritativeAisleFinalization:
    return AuthoritativeAisleFinalization(
        id=normalize_db_str(getattr(row, "id", None)),
        inventory_id=normalize_db_str(getattr(row, "inventory_id", None)),
        aisle_id=normalize_db_str(getattr(row, "aisle_id", None)),
        capture_session_id=optional_nonempty_db_str(getattr(row, "capture_session_id", None)),
        finalization_version=int(getattr(row, "finalization_version", 1) or 1),
        status=normalize_db_str(getattr(row, "status", None)),
        total_assets=int(getattr(row, "total_assets", 0) or 0),
        applied_assets=int(getattr(row, "applied_assets", 0) or 0),
        excluded_assets=int(getattr(row, "excluded_assets", 0) or 0),
        position_count=int(getattr(row, "position_count", 0) or 0),
        expected_asset_count=(
            int(getattr(row, "expected_asset_count"))
            if getattr(row, "expected_asset_count", None) is not None
            else None
        ),
        content_hash=normalize_db_str(getattr(row, "content_hash", None)),
        confirmed_by=normalize_db_str(getattr(row, "confirmed_by", None)),
        confirmed_at=_ensure_utc(getattr(row, "confirmed_at", None)),  # type: ignore[arg-type]
        completed_at=_ensure_utc(getattr(row, "completed_at", None)),
        is_current=bool(getattr(row, "is_current", False)),
        row_version=int(getattr(row, "row_version", 1) or 1),
        created_at=_ensure_utc(getattr(row, "created_at", None)),  # type: ignore[arg-type]
        updated_at=_ensure_utc(getattr(row, "updated_at", None)),  # type: ignore[arg-type]
    )


class SqlAuthoritativeAisleFinalizationRepository:
    def __init__(self, client: SqlServerClient) -> None:
        self._client = client

    def get_by_id(self, finalization_id: str) -> AuthoritativeAisleFinalization | None:
        with self._client.cursor() as cur:
            cur.execute(
                f"SELECT {_FIN_COLS} FROM authoritative_aisle_finalizations WHERE id = ?",
                (finalization_id.strip(),),
            )
            row = cur.fetchone()
        return _fin_from_row(row) if row else None

    def get_current_for_aisle(self, aisle_id: str) -> AuthoritativeAisleFinalization | None:
        with self._client.cursor() as cur:
            cur.execute(
                f"SELECT {_FIN_COLS} FROM authoritative_aisle_finalizations "
                "WHERE aisle_id = ? AND is_current = 1",
                (aisle_id.strip(),),
            )
            row = cur.fetchone()
        return _fin_from_row(row) if row else None

    def max_version_for_aisle(self, aisle_id: str) -> int:
        with self._client.cursor() as cur:
            cur.execute(
                "SELECT MAX(finalization_version) AS max_v FROM authoritative_aisle_finalizations "
                "WHERE aisle_id = ?",
                (aisle_id.strip(),),
            )
            row = cur.fetchone()
        if not row:
            return 0
        val = getattr(row, "max_v", None)
        return int(val or 0)

    def list_items(self, finalization_id: str) -> Sequence[AuthoritativeAisleFinalizationItem]:
        with self._client.cursor() as cur:
            cur.execute(
                "SELECT id, finalization_id, asset_id, authoritative_result_id, position_id, "
                "item_status, created_at FROM authoritative_aisle_finalization_items "
                "WHERE finalization_id = ?",
                (finalization_id.strip(),),
            )
            rows = cur.fetchall()
        return [
            AuthoritativeAisleFinalizationItem(
                id=normalize_db_str(getattr(r, "id", None)),
                finalization_id=normalize_db_str(getattr(r, "finalization_id", None)),
                asset_id=normalize_db_str(getattr(r, "asset_id", None)),
                authoritative_result_id=optional_nonempty_db_str(
                    getattr(r, "authoritative_result_id", None)
                ),
                position_id=optional_nonempty_db_str(getattr(r, "position_id", None)),
                item_status=normalize_db_str(getattr(r, "item_status", None)),
                created_at=_ensure_utc(getattr(r, "created_at", None)),  # type: ignore[arg-type]
            )
            for r in rows
        ]

    def list_current_exclusions(
        self, *, inventory_id: str, aisle_id: str
    ) -> Sequence[AuthoritativeAisleExcludedAsset]:
        with self._client.cursor() as cur:
            cur.execute(
                "SELECT id, inventory_id, aisle_id, asset_id, reason, excluded_by, excluded_at, "
                "is_current, created_at, updated_at FROM authoritative_aisle_excluded_assets "
                "WHERE inventory_id = ? AND aisle_id = ? AND is_current = 1",
                (inventory_id.strip(), aisle_id.strip()),
            )
            rows = cur.fetchall()
        return [
            AuthoritativeAisleExcludedAsset(
                id=normalize_db_str(getattr(r, "id", None)),
                inventory_id=normalize_db_str(getattr(r, "inventory_id", None)),
                aisle_id=normalize_db_str(getattr(r, "aisle_id", None)),
                asset_id=normalize_db_str(getattr(r, "asset_id", None)),
                reason=normalize_db_str(getattr(r, "reason", None)),
                excluded_by=normalize_db_str(getattr(r, "excluded_by", None)),
                excluded_at=_ensure_utc(getattr(r, "excluded_at", None)),  # type: ignore[arg-type]
                is_current=bool(getattr(r, "is_current", False)),
                created_at=_ensure_utc(getattr(r, "created_at", None)),  # type: ignore[arg-type]
                updated_at=_ensure_utc(getattr(r, "updated_at", None)),  # type: ignore[arg-type]
            )
            for r in rows
        ]

    def upsert_exclusion(
        self, row: AuthoritativeAisleExcludedAsset
    ) -> AuthoritativeAisleExcludedAsset:
        with self._client.begin_transaction() as txn:
            cur = txn.connection.cursor()
            cur.execute(
                "UPDATE authoritative_aisle_excluded_assets SET is_current = 0, updated_at = ? "
                "WHERE aisle_id = ? AND asset_id = ? AND is_current = 1",
                (row.updated_at, row.aisle_id, row.asset_id),
            )
            cur.execute(
                "INSERT INTO authoritative_aisle_excluded_assets ("
                "id, inventory_id, aisle_id, asset_id, reason, excluded_by, excluded_at, "
                "is_current, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    row.id,
                    row.inventory_id,
                    row.aisle_id,
                    row.asset_id,
                    row.reason,
                    row.excluded_by,
                    row.excluded_at,
                    1 if row.is_current else 0,
                    row.created_at,
                    row.updated_at,
                ),
            )
        return row

    def save_finalization(
        self,
        *,
        finalization: AuthoritativeAisleFinalization,
        items: Sequence[AuthoritativeAisleFinalizationItem],
        supersede_current: bool,
    ) -> AuthoritativeAisleFinalization:
        with self._client.begin_transaction() as txn:
            cur = txn.connection.cursor()
            if supersede_current:
                cur.execute(
                    "UPDATE authoritative_aisle_finalizations SET is_current = 0, updated_at = ? "
                    "WHERE aisle_id = ? AND is_current = 1",
                    (finalization.updated_at, finalization.aisle_id),
                )
            cur.execute(
                "INSERT INTO authoritative_aisle_finalizations ("
                "id, inventory_id, aisle_id, capture_session_id, finalization_version, status, "
                "total_assets, applied_assets, excluded_assets, position_count, expected_asset_count, "
                "content_hash, confirmed_by, confirmed_at, completed_at, is_current, row_version, "
                "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    finalization.id,
                    finalization.inventory_id,
                    finalization.aisle_id,
                    finalization.capture_session_id,
                    finalization.finalization_version,
                    finalization.status,
                    finalization.total_assets,
                    finalization.applied_assets,
                    finalization.excluded_assets,
                    finalization.position_count,
                    finalization.expected_asset_count,
                    finalization.content_hash,
                    finalization.confirmed_by,
                    finalization.confirmed_at,
                    finalization.completed_at,
                    1 if finalization.is_current else 0,
                    finalization.row_version,
                    finalization.created_at,
                    finalization.updated_at,
                ),
            )
            for item in items:
                cur.execute(
                    "INSERT INTO authoritative_aisle_finalization_items ("
                    "id, finalization_id, asset_id, authoritative_result_id, position_id, "
                    "item_status, created_at) VALUES (?,?,?,?,?,?,?)",
                    (
                        item.id,
                        item.finalization_id,
                        item.asset_id,
                        item.authoritative_result_id,
                        item.position_id,
                        item.item_status,
                        item.created_at,
                    ),
                )
        return finalization

    def try_acquire_lock(
        self,
        *,
        inventory_id: str,
        aisle_id: str,
        owner_token: str,
        lease_expires_at: datetime,
        now: datetime,
    ) -> bool:
        with self._client.begin_transaction() as txn:
            cur = txn.connection.cursor()
            cur.execute(
                "SELECT owner_token, lease_expires_at FROM authoritative_aisle_finalization_locks "
                "WITH (UPDLOCK, HOLDLOCK) WHERE aisle_id = ?",
                (aisle_id,),
            )
            row = cur.fetchone()
            if row is not None:
                token = normalize_db_str(getattr(row, "owner_token", None))
                exp = getattr(row, "lease_expires_at", None)
                if exp is not None and exp > now and token != owner_token:
                    return False
                cur.execute(
                    "UPDATE authoritative_aisle_finalization_locks "
                    "SET inventory_id = ?, owner_token = ?, lease_expires_at = ?, updated_at = ? "
                    "WHERE aisle_id = ?",
                    (inventory_id, owner_token, lease_expires_at, now, aisle_id),
                )
                return True
            cur.execute(
                "INSERT INTO authoritative_aisle_finalization_locks ("
                "inventory_id, aisle_id, owner_token, lease_expires_at, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?)",
                (inventory_id, aisle_id, owner_token, lease_expires_at, now, now),
            )
            return True

    def release_lock(self, *, aisle_id: str, owner_token: str, now: datetime) -> bool:
        del now  # API symmetry; delete is unconditional for owner
        with self._client.begin_transaction() as txn:
            cur = txn.connection.cursor()
            cur.execute(
                "SELECT owner_token FROM authoritative_aisle_finalization_locks WHERE aisle_id = ?",
                (aisle_id,),
            )
            row = cur.fetchone()
            if row is None:
                return True
            if normalize_db_str(getattr(row, "owner_token", None)) != owner_token:
                return False
            cur.execute(
                "DELETE FROM authoritative_aisle_finalization_locks WHERE aisle_id = ?",
                (aisle_id,),
            )
            return True
