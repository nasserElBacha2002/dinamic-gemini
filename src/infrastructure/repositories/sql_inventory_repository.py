"""
SQL Server implementation of InventoryRepository — v3.0 (Épica 2).

Persists Inventory entities to the inventories table. Requires schema from schema.sql (v3 section).
Timestamp policy: domain/use case owns timestamps; repository persists the values it receives
(no repository-generated now_utc() in save()). list_all() ordering: created_at DESC (deterministic).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional, Sequence

from src.application.ports.repositories import InventoryRepository
from src.database.sqlserver import SqlServerClient, now_utc
from src.domain.inventory.entities import Inventory, InventoryStatus

logger = logging.getLogger(__name__)


def _ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Return datetime as timezone-aware UTC (pyodbc may return naive)."""
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt
    return dt.replace(tzinfo=timezone.utc)


class SqlInventoryRepository(InventoryRepository):
    def __init__(self, client: SqlServerClient) -> None:
        self._client = client

    def save(self, inventory: Inventory) -> None:
        """Persist entity; timestamps are taken from the entity (domain-owned)."""
        completed = _ensure_utc(inventory.completed_at)
        created = _ensure_utc(inventory.created_at)
        updated = _ensure_utc(inventory.updated_at)
        with self._client.cursor() as cur:
            cur.execute(
                """
                UPDATE inventories
                SET name = ?, status = ?, updated_at = ?, completed_at = ?
                WHERE id = ?
                """,
                (inventory.name, inventory.status.value, updated, completed, inventory.id),
            )
            if cur.rowcount == 0:
                cur.execute(
                    """
                    INSERT INTO inventories (id, name, status, created_at, updated_at, completed_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        inventory.id,
                        inventory.name,
                        inventory.status.value,
                        created,
                        updated,
                        completed,
                    ),
                )

    def get_by_id(self, inventory_id: str) -> Optional[Inventory]:
        with self._client.cursor() as cur:
            cur.execute(
                """
                SELECT id, name, status, created_at, updated_at, completed_at
                FROM inventories WHERE id = ?
                """,
                (inventory_id,),
            )
            row = cur.fetchone()
        if not row:
            return None
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
        return Inventory(
            id=row.id,
            name=row.name or "",
            status=status,
            created_at=_ensure_utc(row.created_at) or now_utc(),
            updated_at=_ensure_utc(row.updated_at) or now_utc(),
            completed_at=_ensure_utc(getattr(row, "completed_at", None)),
        )

    def list_all(self) -> Sequence[Inventory]:
        """Return all inventories; order is created_at DESC (deterministic)."""
        with self._client.cursor() as cur:
            cur.execute(
                """
                SELECT id, name, status, created_at, updated_at, completed_at
                FROM inventories ORDER BY created_at DESC
                """
            )
            rows = cur.fetchall()
        out = []
        for row in rows:
            status_str = getattr(row, "status", "draft") or "draft"
            try:
                status = InventoryStatus(status_str)
            except ValueError:
                logger.warning(
                    "Invalid inventory status from DB: %r, using DRAFT for inventory_id=%s",
                    status_str,
                    getattr(row, "id", "?"),
                )
                status = InventoryStatus.DRAFT
            out.append(
                Inventory(
                    id=row.id,
                    name=row.name or "",
                    status=status,
                    created_at=_ensure_utc(row.created_at) or now_utc(),
                    updated_at=_ensure_utc(row.updated_at) or now_utc(),
                    completed_at=_ensure_utc(getattr(row, "completed_at", None)),
                )
            )
        return out
