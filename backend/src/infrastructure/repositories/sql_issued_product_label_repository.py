"""SQL Server issued product label registry."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol

from src.application.errors import ProductLabelIdCollisionError
from src.application.ports.issued_product_label_repository import (
    IssuedProductLabel,
    IssuedProductLabelRepository,
)
from src.database.sqlserver import SqlServerClient
from src.infrastructure.database.sql_transaction import sql_repository_cursor
from src.infrastructure.database.sql_unique_violation import is_sql_unique_violation


class _IssuedProductLabelRow(Protocol):
    id: object
    client_id: object
    label_id: object
    internal_code: object
    quantity: object
    format_version: object
    checksum: object
    payload: object
    created_at: datetime
    created_by: object | None


def _as_sql_datetime(value: datetime) -> datetime:
    """DATETIME2 is timezone-naive; strip tz after normalizing to UTC."""
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


class SqlIssuedProductLabelRepository(IssuedProductLabelRepository):
    def __init__(self, client: SqlServerClient, *, connection: object | None = None) -> None:
        self._client = client
        self._connection = connection

    def save(self, row: IssuedProductLabel) -> None:
        try:
            with sql_repository_cursor(self._client, connection=self._connection) as cur:
                cur.execute(
                    """
                    INSERT INTO issued_product_labels (
                        id, client_id, label_id, internal_code, quantity,
                        format_version, checksum, payload, created_at, created_by
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row.id,
                        row.client_id,
                        row.label_id.upper(),
                        row.internal_code,
                        row.quantity,
                        row.format_version,
                        row.checksum,
                        row.payload,
                        _as_sql_datetime(row.created_at),
                        row.created_by,
                    ),
                )
        except Exception as exc:
            if is_sql_unique_violation(exc):
                raise ProductLabelIdCollisionError(
                    f"duplicate label_id: {row.label_id}"
                ) from exc
            raise

    def get_by_label_id(self, label_id: str) -> IssuedProductLabel | None:
        with sql_repository_cursor(self._client, connection=self._connection) as cur:
            cur.execute(
                """
                SELECT id, client_id, label_id, internal_code, quantity,
                       format_version, checksum, payload, created_at, created_by
                FROM issued_product_labels
                WHERE label_id = ?
                """,
                (label_id.upper(),),
            )
            row = cur.fetchone()
        if not row:
            return None
        return self._map(row)

    def list_by_client(
        self, client_id: str, *, limit: int = 50, offset: int = 0
    ) -> list[IssuedProductLabel]:
        with sql_repository_cursor(self._client, connection=self._connection) as cur:
            cur.execute(
                """
                SELECT id, client_id, label_id, internal_code, quantity,
                       format_version, checksum, payload, created_at, created_by
                FROM issued_product_labels
                WHERE client_id = ?
                ORDER BY created_at DESC
                OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
                """,
                (client_id, offset, limit),
            )
            rows = cur.fetchall()
        return [self._map(r) for r in rows]

    @staticmethod
    def _map(row: _IssuedProductLabelRow) -> IssuedProductLabel:
        created = row.created_at
        if created is not None and created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        return IssuedProductLabel(
            id=str(row.id),
            client_id=str(row.client_id),
            label_id=str(row.label_id),
            internal_code=str(row.internal_code),
            quantity=int(str(row.quantity)),
            format_version=str(row.format_version),
            checksum=str(row.checksum),
            payload=str(row.payload),
            created_at=created,
            created_by=str(row.created_by) if row.created_by is not None else None,
        )
