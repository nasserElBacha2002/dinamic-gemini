"""SQL Server aisle revision repository (Phase 8)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone

from src.database.sqlserver import SqlServerClient
from src.domain.aisle_revision.entities import (
    AisleRevision,
    AisleRevisionItem,
    PositionVersion,
    revision_is_open,
)
from src.infrastructure.repositories.db_row_text import normalize_db_str, optional_nonempty_db_str

_REV_COLS = (
    "id, inventory_id, aisle_id, base_finalization_id, new_finalization_id, revision_type, "
    "status, reason, requested_by, requested_at, started_at, completed_at, canceled_at, "
    "failed_at, failure_code, failure_message, apply_id, snapshot_json, content_hash, "
    "row_version, created_at, updated_at"
)


def _utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _rev_from_row(row) -> AisleRevision:
    return AisleRevision(
        id=normalize_db_str(getattr(row, "id", None)),
        inventory_id=normalize_db_str(getattr(row, "inventory_id", None)),
        aisle_id=normalize_db_str(getattr(row, "aisle_id", None)),
        base_finalization_id=normalize_db_str(getattr(row, "base_finalization_id", None)),
        new_finalization_id=optional_nonempty_db_str(getattr(row, "new_finalization_id", None)),
        revision_type=normalize_db_str(getattr(row, "revision_type", None)),
        status=normalize_db_str(getattr(row, "status", None)),
        reason=normalize_db_str(getattr(row, "reason", None)),
        requested_by=normalize_db_str(getattr(row, "requested_by", None)),
        requested_at=_utc(getattr(row, "requested_at", None)),  # type: ignore[arg-type]
        started_at=_utc(getattr(row, "started_at", None)),
        completed_at=_utc(getattr(row, "completed_at", None)),
        canceled_at=_utc(getattr(row, "canceled_at", None)),
        failed_at=_utc(getattr(row, "failed_at", None)),
        failure_code=optional_nonempty_db_str(getattr(row, "failure_code", None)),
        failure_message=optional_nonempty_db_str(getattr(row, "failure_message", None)),
        apply_id=optional_nonempty_db_str(getattr(row, "apply_id", None)),
        snapshot_json=normalize_db_str(getattr(row, "snapshot_json", None)) or "{}",
        content_hash=normalize_db_str(getattr(row, "content_hash", None)),
        row_version=int(getattr(row, "row_version", 1) or 1),
        created_at=_utc(getattr(row, "created_at", None)),  # type: ignore[arg-type]
        updated_at=_utc(getattr(row, "updated_at", None)),  # type: ignore[arg-type]
    )


def _item_from_row(row) -> AisleRevisionItem:
    return AisleRevisionItem(
        id=normalize_db_str(getattr(row, "id", None)),
        revision_id=normalize_db_str(getattr(row, "revision_id", None)),
        asset_id=normalize_db_str(getattr(row, "asset_id", None)),
        base_result_id=optional_nonempty_db_str(getattr(row, "base_result_id", None)),
        base_position_id=optional_nonempty_db_str(getattr(row, "base_position_id", None)),
        proposed_internal_code=optional_nonempty_db_str(
            getattr(row, "proposed_internal_code", None)
        ),
        proposed_quantity=(
            int(getattr(row, "proposed_quantity"))
            if getattr(row, "proposed_quantity", None) is not None
            else None
        ),
        proposed_exclusion_state=optional_nonempty_db_str(
            getattr(row, "proposed_exclusion_state", None)
        ),
        proposal_source=normalize_db_str(getattr(row, "proposal_source", None)),
        proposal_reference_id=optional_nonempty_db_str(
            getattr(row, "proposal_reference_id", None)
        ),
        change_reason=optional_nonempty_db_str(getattr(row, "change_reason", None)),
        item_status=normalize_db_str(getattr(row, "item_status", None)),
        created_at=_utc(getattr(row, "created_at", None)),  # type: ignore[arg-type]
        updated_at=_utc(getattr(row, "updated_at", None)),  # type: ignore[arg-type]
    )


def _pv_from_row(row) -> PositionVersion:
    return PositionVersion(
        id=normalize_db_str(getattr(row, "id", None)),
        position_id=normalize_db_str(getattr(row, "position_id", None)),
        version=int(getattr(row, "version", 1) or 1),
        aisle_id=normalize_db_str(getattr(row, "aisle_id", None)),
        asset_id=normalize_db_str(getattr(row, "asset_id", None)),
        internal_code=normalize_db_str(getattr(row, "internal_code", None)),
        quantity=(
            int(getattr(row, "quantity"))
            if getattr(row, "quantity", None) is not None
            else None
        ),
        result_id=optional_nonempty_db_str(getattr(row, "result_id", None)),
        is_current=bool(getattr(row, "is_current", False)),
        supersedes_position_version_id=optional_nonempty_db_str(
            getattr(row, "supersedes_position_version_id", None)
        ),
        revision_id=optional_nonempty_db_str(getattr(row, "revision_id", None)),
        revision_item_id=optional_nonempty_db_str(getattr(row, "revision_item_id", None)),
        created_by=normalize_db_str(getattr(row, "created_by", None)),
        created_at=_utc(getattr(row, "created_at", None)),  # type: ignore[arg-type]
        content_hash=normalize_db_str(getattr(row, "content_hash", None)),
    )


class SqlAisleRevisionRepository:
    def __init__(self, client: SqlServerClient) -> None:
        self._client = client

    def get_revision(self, revision_id: str) -> AisleRevision | None:
        with self._client.cursor() as cur:
            cur.execute(
                f"SELECT {_REV_COLS} FROM aisle_revisions WHERE id = ?",
                (revision_id.strip(),),
            )
            row = cur.fetchone()
        return _rev_from_row(row) if row else None

    def get_open_revision_for_aisle(self, aisle_id: str) -> AisleRevision | None:
        with self._client.cursor() as cur:
            cur.execute(
                f"SELECT TOP 1 {_REV_COLS} FROM aisle_revisions WHERE aisle_id = ? "
                "AND status IN ('DRAFT','OPEN','IN_REVIEW','READY_TO_APPLY','APPLYING') "
                "ORDER BY requested_at DESC",
                (aisle_id.strip(),),
            )
            row = cur.fetchone()
        return _rev_from_row(row) if row else None

    def list_revisions_for_aisle(
        self, *, aisle_id: str, limit: int = 50
    ) -> Sequence[AisleRevision]:
        lim = max(1, min(int(limit), 200))
        with self._client.cursor() as cur:
            cur.execute(
                f"SELECT TOP ({lim}) {_REV_COLS} FROM aisle_revisions WHERE aisle_id = ? "
                "ORDER BY requested_at DESC",
                (aisle_id.strip(),),
            )
            rows = cur.fetchall()
        return [_rev_from_row(r) for r in rows]

    def list_items(self, revision_id: str) -> Sequence[AisleRevisionItem]:
        with self._client.cursor() as cur:
            cur.execute(
                "SELECT id, revision_id, asset_id, base_result_id, base_position_id, "
                "proposed_internal_code, proposed_quantity, proposed_exclusion_state, "
                "proposal_source, proposal_reference_id, change_reason, item_status, "
                "created_at, updated_at FROM aisle_revision_items WHERE revision_id = ?",
                (revision_id.strip(),),
            )
            rows = cur.fetchall()
        return [_item_from_row(r) for r in rows]

    def get_item(self, *, revision_id: str, asset_id: str) -> AisleRevisionItem | None:
        with self._client.cursor() as cur:
            cur.execute(
                "SELECT id, revision_id, asset_id, base_result_id, base_position_id, "
                "proposed_internal_code, proposed_quantity, proposed_exclusion_state, "
                "proposal_source, proposal_reference_id, change_reason, item_status, "
                "created_at, updated_at FROM aisle_revision_items "
                "WHERE revision_id = ? AND asset_id = ?",
                (revision_id.strip(), asset_id.strip()),
            )
            row = cur.fetchone()
        return _item_from_row(row) if row else None

    def save_revision(
        self,
        revision: AisleRevision,
        *,
        items: Sequence[AisleRevisionItem] | None = None,
    ) -> AisleRevision:
        with self._client.begin_transaction() as txn:
            cur = txn.connection.cursor()
            cur.execute("SELECT id FROM aisle_revisions WHERE id = ?", (revision.id,))
            exists = cur.fetchone() is not None
            vals = (
                revision.inventory_id,
                revision.aisle_id,
                revision.base_finalization_id,
                revision.new_finalization_id,
                revision.revision_type,
                revision.status,
                revision.reason,
                revision.requested_by,
                revision.requested_at,
                revision.started_at,
                revision.completed_at,
                revision.canceled_at,
                revision.failed_at,
                revision.failure_code,
                revision.failure_message,
                revision.apply_id,
                revision.snapshot_json,
                revision.content_hash,
                revision.row_version,
                revision.updated_at,
                revision.id,
            )
            if exists:
                cur.execute(
                    "UPDATE aisle_revisions SET inventory_id=?, aisle_id=?, base_finalization_id=?, "
                    "new_finalization_id=?, revision_type=?, status=?, reason=?, requested_by=?, "
                    "requested_at=?, started_at=?, completed_at=?, canceled_at=?, failed_at=?, "
                    "failure_code=?, failure_message=?, apply_id=?, snapshot_json=?, content_hash=?, "
                    "row_version=?, updated_at=? WHERE id=?",
                    vals,
                )
            else:
                cur.execute(
                    "INSERT INTO aisle_revisions ("
                    "id, inventory_id, aisle_id, base_finalization_id, new_finalization_id, "
                    "revision_type, status, reason, requested_by, requested_at, started_at, "
                    "completed_at, canceled_at, failed_at, failure_code, failure_message, apply_id, "
                    "snapshot_json, content_hash, row_version, created_at, updated_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        revision.id,
                        revision.inventory_id,
                        revision.aisle_id,
                        revision.base_finalization_id,
                        revision.new_finalization_id,
                        revision.revision_type,
                        revision.status,
                        revision.reason,
                        revision.requested_by,
                        revision.requested_at,
                        revision.started_at,
                        revision.completed_at,
                        revision.canceled_at,
                        revision.failed_at,
                        revision.failure_code,
                        revision.failure_message,
                        revision.apply_id,
                        revision.snapshot_json,
                        revision.content_hash,
                        revision.row_version,
                        revision.created_at,
                        revision.updated_at,
                    ),
                )
            if items is not None:
                cur.execute(
                    "DELETE FROM aisle_revision_items WHERE revision_id = ?",
                    (revision.id,),
                )
                for item in items:
                    self._insert_item(cur, item)
            if revision_is_open(revision.status):
                # projection helper
                cur.execute(
                    "UPDATE aisles SET revision_status = ?, updated_at = ? WHERE id = ?",
                    (revision.status, revision.updated_at, revision.aisle_id),
                )
            elif revision.status in ("COMPLETED", "CANCELED", "FAILED", "CONFLICTED"):
                cur.execute(
                    "UPDATE aisles SET revision_status = NULL, updated_at = ? WHERE id = ?",
                    (revision.updated_at, revision.aisle_id),
                )
        return revision

    def _insert_item(self, cur, item: AisleRevisionItem) -> None:
        cur.execute(
            "INSERT INTO aisle_revision_items ("
            "id, revision_id, asset_id, base_result_id, base_position_id, "
            "proposed_internal_code, proposed_quantity, proposed_exclusion_state, "
            "proposal_source, proposal_reference_id, change_reason, item_status, "
            "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                item.id,
                item.revision_id,
                item.asset_id,
                item.base_result_id,
                item.base_position_id,
                item.proposed_internal_code,
                item.proposed_quantity,
                item.proposed_exclusion_state,
                item.proposal_source,
                item.proposal_reference_id,
                item.change_reason,
                item.item_status,
                item.created_at,
                item.updated_at,
            ),
        )

    def save_item(self, item: AisleRevisionItem) -> AisleRevisionItem:
        with self._client.begin_transaction() as txn:
            cur = txn.connection.cursor()
            cur.execute(
                "DELETE FROM aisle_revision_items WHERE revision_id = ? AND asset_id = ?",
                (item.revision_id, item.asset_id),
            )
            self._insert_item(cur, item)
        return item

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
                "SELECT owner_token, lease_expires_at FROM aisle_revision_locks "
                "WITH (UPDLOCK, HOLDLOCK) WHERE aisle_id = ?",
                (aisle_id,),
            )
            row = cur.fetchone()
            if row is not None:
                token = normalize_db_str(getattr(row, "owner_token", None))
                exp = _utc(getattr(row, "lease_expires_at", None))
                if exp and exp > now and token != owner_token:
                    return False
                cur.execute(
                    "UPDATE aisle_revision_locks SET inventory_id=?, owner_token=?, "
                    "lease_expires_at=?, updated_at=? WHERE aisle_id=?",
                    (inventory_id, owner_token, lease_expires_at, now, aisle_id),
                )
            else:
                cur.execute(
                    "INSERT INTO aisle_revision_locks ("
                    "inventory_id, aisle_id, owner_token, lease_expires_at, created_at, updated_at) "
                    "VALUES (?,?,?,?,?,?)",
                    (inventory_id, aisle_id, owner_token, lease_expires_at, now, now),
                )
        return True

    def release_lock(self, *, aisle_id: str, owner_token: str, now: datetime) -> bool:
        del now
        with self._client.begin_transaction() as txn:
            cur = txn.connection.cursor()
            cur.execute(
                "DELETE FROM aisle_revision_locks WHERE aisle_id = ? AND owner_token = ?",
                (aisle_id, owner_token),
            )
        return True

    def get_current_position_version(self, position_id: str) -> PositionVersion | None:
        with self._client.cursor() as cur:
            cur.execute(
                "SELECT TOP 1 id, position_id, version, aisle_id, asset_id, internal_code, "
                "quantity, result_id, is_current, supersedes_position_version_id, revision_id, "
                "revision_item_id, created_by, created_at, content_hash "
                "FROM position_versions WHERE position_id = ? AND is_current = 1",
                (position_id.strip(),),
            )
            row = cur.fetchone()
        return _pv_from_row(row) if row else None

    def max_position_version(self, position_id: str) -> int:
        with self._client.cursor() as cur:
            cur.execute(
                "SELECT MAX(version) AS max_v FROM position_versions WHERE position_id = ?",
                (position_id.strip(),),
            )
            row = cur.fetchone()
        return int(getattr(row, "max_v", None) or 0) if row else 0

    def save_position_version(
        self,
        row: PositionVersion,
        *,
        supersede_current: bool,
    ) -> PositionVersion:
        with self._client.begin_transaction() as txn:
            cur = txn.connection.cursor()
            if supersede_current:
                cur.execute(
                    "UPDATE position_versions SET is_current = 0 WHERE position_id = ? AND is_current = 1",
                    (row.position_id,),
                )
            cur.execute(
                "INSERT INTO position_versions ("
                "id, position_id, version, aisle_id, asset_id, internal_code, quantity, "
                "result_id, is_current, supersedes_position_version_id, revision_id, "
                "revision_item_id, created_by, created_at, content_hash) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    row.id,
                    row.position_id,
                    row.version,
                    row.aisle_id,
                    row.asset_id,
                    row.internal_code,
                    row.quantity,
                    row.result_id,
                    1 if row.is_current else 0,
                    row.supersedes_position_version_id,
                    row.revision_id,
                    row.revision_item_id,
                    row.created_by,
                    row.created_at,
                    row.content_hash,
                ),
            )
        return row

    def list_position_versions_for_aisle(
        self, *, aisle_id: str, limit: int = 500
    ) -> Sequence[PositionVersion]:
        lim = max(1, min(int(limit), 2000))
        with self._client.cursor() as cur:
            cur.execute(
                f"SELECT TOP ({lim}) id, position_id, version, aisle_id, asset_id, internal_code, "
                "quantity, result_id, is_current, supersedes_position_version_id, revision_id, "
                "revision_item_id, created_by, created_at, content_hash "
                "FROM position_versions WHERE aisle_id = ? ORDER BY created_at DESC",
                (aisle_id.strip(),),
            )
            rows = cur.fetchall()
        return [_pv_from_row(r) for r in rows]
