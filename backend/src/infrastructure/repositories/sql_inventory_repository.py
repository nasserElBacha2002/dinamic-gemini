"""
SQL Server implementation of InventoryRepository — v3.0 (Épica 2).

Persists Inventory entities to the inventories table. Requires schema from schema.sql (v3 section).
Timestamp policy: domain/use case owns timestamps; repository persists the values it receives
(no repository-generated now_utc() in save()). list_all() ordering: created_at DESC (deterministic).
list_all() excludes soft-deleted rows (deleted_at IS NULL). get_by_id() returns deleted rows so
in-flight workers can finish; API/use cases must reject deleted via InventoryAccessPolicy /
reject_if_inventory_deleted.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import datetime, timezone

from src.application.ports.repositories import InventoryRepository
from src.database.sqlserver import SqlServerClient, now_utc
from src.domain.aisle_identification.modes import optional_config_identification_mode
from src.domain.inventory.entities import (
    Inventory,
    InventoryProcessingMode,
    InventoryStatus,
)
from src.infrastructure.database.sql_transaction import sql_repository_cursor

logger = logging.getLogger(__name__)

_INVENTORY_SELECT_COLUMNS = """
                id, name, status, created_at, updated_at, completed_at,
                processing_mode, primary_provider_name, primary_model_name,
                primary_prompt_key, primary_prompt_version, client_id,
                identification_mode, deleted_at, deleted_by
"""


def _ensure_utc(dt: datetime | None) -> datetime | None:
    """Return datetime as timezone-aware UTC (pyodbc may return naive)."""
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt
    return dt.replace(tzinfo=timezone.utc)


class SqlInventoryRepository(InventoryRepository):
    def __init__(self, client: SqlServerClient, *, connection: object | None = None) -> None:
        self._client = client
        self._connection = connection

    def _row_processing_mode(self, raw: object, inventory_id: str) -> InventoryProcessingMode:
        s = (raw or "production") if raw is not None else "production"
        s = str(s).strip().lower()
        try:
            return InventoryProcessingMode(s)
        except ValueError:
            logger.warning(
                "Invalid inventory processing_mode from DB: %r, using PRODUCTION for inventory_id=%s",
                raw,
                inventory_id,
            )
            return InventoryProcessingMode.PRODUCTION

    def _row_to_inventory(self, row: object) -> Inventory:
        inventory_id = str(getattr(row, "id", "?"))
        status_str = getattr(row, "status", "draft") or "draft"
        try:
            status = InventoryStatus(status_str)
        except ValueError:
            logger.warning(
                "Invalid inventory status from DB: %r, using DRAFT for inventory_id=%s",
                status_str,
                inventory_id,
            )
            status = InventoryStatus.DRAFT
        pm = self._row_processing_mode(getattr(row, "processing_mode", None), inventory_id)
        return Inventory(
            id=row.id,  # type: ignore[attr-defined]
            name=row.name or "",  # type: ignore[attr-defined]
            status=status,
            created_at=_ensure_utc(row.created_at) or now_utc(),  # type: ignore[attr-defined]
            updated_at=_ensure_utc(row.updated_at) or now_utc(),  # type: ignore[attr-defined]
            completed_at=_ensure_utc(getattr(row, "completed_at", None)),
            processing_mode=pm,
            primary_provider_name=getattr(row, "primary_provider_name", None),
            primary_model_name=getattr(row, "primary_model_name", None),
            primary_prompt_key=getattr(row, "primary_prompt_key", None),
            primary_prompt_version=getattr(row, "primary_prompt_version", None),
            client_id=getattr(row, "client_id", None),
            identification_mode=optional_config_identification_mode(
                getattr(row, "identification_mode", None)
            ),
            deleted_at=_ensure_utc(getattr(row, "deleted_at", None)),
            deleted_by=getattr(row, "deleted_by", None),
        )

    def save(self, inventory: Inventory) -> None:
        """Persist entity; timestamps are taken from the entity (domain-owned)."""
        completed = _ensure_utc(inventory.completed_at)
        created = _ensure_utc(inventory.created_at)
        updated = _ensure_utc(inventory.updated_at)
        deleted_at = _ensure_utc(inventory.deleted_at)
        with sql_repository_cursor(self._client, connection=self._connection) as cur:
            cur.execute(
                """
                UPDATE inventories
                SET name = ?, status = ?, updated_at = ?, completed_at = ?,
                    processing_mode = ?, primary_provider_name = ?, primary_model_name = ?,
                    primary_prompt_key = ?, primary_prompt_version = ?, client_id = ?,
                    identification_mode = ?, deleted_at = ?, deleted_by = ?
                WHERE id = ?
                """,
                (
                    inventory.name,
                    inventory.status.value,
                    updated,
                    completed,
                    inventory.processing_mode.value,
                    inventory.primary_provider_name,
                    inventory.primary_model_name,
                    inventory.primary_prompt_key,
                    inventory.primary_prompt_version,
                    inventory.client_id,
                    inventory.identification_mode.value if inventory.identification_mode else None,
                    deleted_at,
                    inventory.deleted_by,
                    inventory.id,
                ),
            )
            if cur.rowcount == 0:
                cur.execute(
                    """
                    INSERT INTO inventories (
                        id, name, status, created_at, updated_at, completed_at,
                        processing_mode, primary_provider_name, primary_model_name,
                        primary_prompt_key, primary_prompt_version, client_id,
                        identification_mode, deleted_at, deleted_by
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        inventory.id,
                        inventory.name,
                        inventory.status.value,
                        created,
                        updated,
                        completed,
                        inventory.processing_mode.value,
                        inventory.primary_provider_name,
                        inventory.primary_model_name,
                        inventory.primary_prompt_key,
                        inventory.primary_prompt_version,
                        inventory.client_id,
                        inventory.identification_mode.value
                        if inventory.identification_mode
                        else None,
                        deleted_at,
                        inventory.deleted_by,
                    ),
                )

    def compare_and_set_status(
        self,
        inventory_id: str,
        *,
        expected_current: InventoryStatus,
        new_status: InventoryStatus,
        updated_at: datetime,
        completed_at: datetime | None,
    ) -> bool:
        """Atomic status transition: UPDATE only when current status matches ``expected_current``."""
        with sql_repository_cursor(self._client, connection=self._connection) as cur:
            cur.execute(
                """
                UPDATE inventories
                SET status = ?, updated_at = ?, completed_at = ?
                WHERE id = ? AND status = ?
                """,
                (
                    new_status.value,
                    _ensure_utc(updated_at),
                    _ensure_utc(completed_at),
                    inventory_id,
                    expected_current.value,
                ),
            )
            return int(cur.rowcount or 0) > 0

    def get_by_id(self, inventory_id: str) -> Inventory | None:
        with sql_repository_cursor(self._client, connection=self._connection) as cur:
            cur.execute(
                f"""
                SELECT {_INVENTORY_SELECT_COLUMNS}
                FROM inventories WHERE id = ?
                """,
                (inventory_id,),
            )
            row = cur.fetchone()
        if not row:
            return None
        return self._row_to_inventory(row)

    def list_all(self) -> Sequence[Inventory]:
        """Return active inventories (deleted_at IS NULL); order is created_at DESC."""
        with sql_repository_cursor(self._client, connection=self._connection) as cur:
            cur.execute(
                f"""
                SELECT {_INVENTORY_SELECT_COLUMNS}
                FROM inventories
                WHERE deleted_at IS NULL
                ORDER BY created_at DESC
                """
            )
            rows = cur.fetchall()
        return [self._row_to_inventory(row) for row in rows]
