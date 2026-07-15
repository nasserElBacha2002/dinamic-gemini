"""
SQL Server implementation of AisleRepository — v3.0 (Épica 3).

Persists Aisle entities to the aisles table. Timestamp policy: domain/use case owns timestamps.
list_by_inventory ordering: created_at DESC (deterministic).
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import datetime, timezone

from src.application.ports.repositories import AisleRepository
from src.database.sqlserver import SqlServerClient
from src.domain.aisle.entities import Aisle, AisleStatus

logger = logging.getLogger(__name__)


def _ensure_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt
    return dt.replace(tzinfo=timezone.utc)


def _status_from_row(row, aisle_id: str = "?") -> AisleStatus:
    status_str = getattr(row, "status", "created") or "created"
    try:
        return AisleStatus(status_str)
    except ValueError:
        logger.warning(
            "Invalid aisle status from DB: %r, using CREATED for aisle_id=%s",
            status_str,
            aisle_id,
        )
        return AisleStatus.CREATED


def _row_to_aisle(row) -> Aisle:
    aid = getattr(row, "id", "")
    created = _ensure_utc(getattr(row, "created_at", None))
    updated = _ensure_utc(getattr(row, "updated_at", None))
    if created is None:
        logger.warning("Aisle row missing created_at for aisle_id=%s", aid)
        raise ValueError("Aisle row missing required created_at")
    if updated is None:
        logger.warning("Aisle row missing updated_at for aisle_id=%s", aid)
        raise ValueError("Aisle row missing required updated_at")
    return Aisle(
        id=aid,
        inventory_id=row.inventory_id or "",
        code=row.code or "",
        status=_status_from_row(row, aid),
        created_at=created,
        updated_at=updated,
        operational_job_id=getattr(row, "operational_job_id", None),
        client_supplier_id=getattr(row, "client_supplier_id", None),
        error_code=getattr(row, "error_code", None),
        error_message=getattr(row, "error_message", None),
        retryable=getattr(row, "retryable", None),
        is_active=bool(getattr(row, "is_active", True)),
    )


class SqlAisleRepository(AisleRepository):
    def __init__(self, client: SqlServerClient) -> None:
        self._client = client

    def save(self, aisle: Aisle) -> None:
        if aisle.created_at is None or aisle.updated_at is None:
            raise ValueError("Aisle created_at and updated_at are required")
        created = _ensure_utc(aisle.created_at)
        updated = _ensure_utc(aisle.updated_at)
        is_active_bit = 1 if aisle.is_active else 0
        with self._client.cursor() as cur:
            cur.execute(
                """
                UPDATE aisles
                SET inventory_id = ?, code = ?, status = ?, updated_at = ?,
                    operational_job_id = ?,
                    client_supplier_id = ?,
                    error_code = ?, error_message = ?, retryable = ?,
                    is_active = ?
                WHERE id = ?
                """,
                (
                    aisle.inventory_id,
                    aisle.code,
                    aisle.status.value,
                    updated,
                    aisle.operational_job_id,
                    aisle.client_supplier_id,
                    aisle.error_code,
                    aisle.error_message,
                    aisle.retryable,
                    is_active_bit,
                    aisle.id,
                ),
            )
            if cur.rowcount == 0:
                cur.execute(
                    """
                    INSERT INTO aisles (
                        id, inventory_id, code, status, created_at, updated_at,
                        operational_job_id, client_supplier_id, error_code, error_message, retryable,
                        is_active
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        aisle.id,
                        aisle.inventory_id,
                        aisle.code,
                        aisle.status.value,
                        created,
                        updated,
                        aisle.operational_job_id,
                        aisle.client_supplier_id,
                        aisle.error_code,
                        aisle.error_message,
                        aisle.retryable,
                        is_active_bit,
                    ),
                )

    def get_by_id(self, aisle_id: str) -> Aisle | None:
        with self._client.cursor() as cur:
            cur.execute(
                """
                SELECT id, inventory_id, code, status, created_at, updated_at,
                       operational_job_id, client_supplier_id, error_code, error_message, retryable,
                       is_active
                FROM aisles WHERE id = ?
                """,
                (aisle_id,),
            )
            row = cur.fetchone()
        if not row:
            return None
        return _row_to_aisle(row)

    def list_by_inventory(self, inventory_id: str) -> Sequence[Aisle]:
        with self._client.cursor() as cur:
            cur.execute(
                """
                SELECT id, inventory_id, code, status, created_at, updated_at,
                       operational_job_id, client_supplier_id, error_code, error_message, retryable,
                       is_active
                FROM aisles WHERE inventory_id = ? ORDER BY created_at DESC
                """,
                (inventory_id,),
            )
            rows = cur.fetchall()
        return [_row_to_aisle(row) for row in rows]

    def get_by_inventory_and_code(self, inventory_id: str, code: str) -> Aisle | None:
        with self._client.cursor() as cur:
            cur.execute(
                """
                SELECT id, inventory_id, code, status, created_at, updated_at,
                       operational_job_id, client_supplier_id, error_code, error_message, retryable,
                       is_active
                FROM aisles WHERE inventory_id = ? AND code = ?
                """,
                (inventory_id, code.strip()),
            )
            row = cur.fetchone()
        if not row:
            return None
        return _row_to_aisle(row)
