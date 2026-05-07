"""SQL Server implementation of ClientSupplierRepository — Phase A2 foundation."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone

from src.application.ports.repositories import ClientSupplierRepository
from src.database.sqlserver import SqlServerClient, now_utc
from src.domain.client_supplier.entities import ClientSupplier, ClientSupplierStatus


def _ensure_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt
    return dt.replace(tzinfo=timezone.utc)


class SqlClientSupplierRepository(ClientSupplierRepository):
    def __init__(self, client: SqlServerClient) -> None:
        self._client = client

    def save(self, supplier: ClientSupplier) -> None:
        created = _ensure_utc(supplier.created_at)
        updated = _ensure_utc(supplier.updated_at)
        with self._client.cursor() as cur:
            cur.execute(
                """
                UPDATE client_suppliers
                SET client_id = ?, name = ?, status = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    supplier.client_id,
                    supplier.name,
                    supplier.status.value,
                    updated,
                    supplier.id,
                ),
            )
            if cur.rowcount == 0:
                cur.execute(
                    """
                    INSERT INTO client_suppliers (id, client_id, name, status, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        supplier.id,
                        supplier.client_id,
                        supplier.name,
                        supplier.status.value,
                        created,
                        updated,
                    ),
                )

    def get_by_id(self, supplier_id: str) -> ClientSupplier | None:
        with self._client.cursor() as cur:
            cur.execute(
                """
                SELECT id, client_id, name, status, created_at, updated_at
                FROM client_suppliers
                WHERE id = ?
                """,
                (supplier_id,),
            )
            row = cur.fetchone()
        if not row:
            return None
        status_raw = str(
            getattr(row, "status", ClientSupplierStatus.ACTIVE.value)
            or ClientSupplierStatus.ACTIVE.value
        )
        try:
            status = ClientSupplierStatus(status_raw)
        except ValueError:
            status = ClientSupplierStatus.ACTIVE
        return ClientSupplier(
            id=row.id,
            client_id=row.client_id,
            name=row.name or "",
            status=status,
            created_at=_ensure_utc(row.created_at) or now_utc(),
            updated_at=_ensure_utc(row.updated_at) or now_utc(),
        )

    def get_by_client_and_name(self, client_id: str, name: str) -> ClientSupplier | None:
        with self._client.cursor() as cur:
            cur.execute(
                """
                SELECT id, client_id, name, status, created_at, updated_at
                FROM client_suppliers
                WHERE client_id = ? AND name = ?
                """,
                (client_id, name),
            )
            row = cur.fetchone()
        if not row:
            return None
        status_raw = str(
            getattr(row, "status", ClientSupplierStatus.ACTIVE.value)
            or ClientSupplierStatus.ACTIVE.value
        )
        try:
            status = ClientSupplierStatus(status_raw)
        except ValueError:
            status = ClientSupplierStatus.ACTIVE
        return ClientSupplier(
            id=row.id,
            client_id=row.client_id,
            name=row.name or "",
            status=status,
            created_at=_ensure_utc(row.created_at) or now_utc(),
            updated_at=_ensure_utc(row.updated_at) or now_utc(),
        )

    def list_by_client(self, client_id: str) -> Sequence[ClientSupplier]:
        with self._client.cursor() as cur:
            cur.execute(
                """
                SELECT id, client_id, name, status, created_at, updated_at
                FROM client_suppliers
                WHERE client_id = ?
                ORDER BY created_at DESC
                """,
                (client_id,),
            )
            rows = cur.fetchall()
        out: list[ClientSupplier] = []
        for row in rows:
            status_raw = str(
                getattr(row, "status", ClientSupplierStatus.ACTIVE.value)
                or ClientSupplierStatus.ACTIVE.value
            )
            try:
                status = ClientSupplierStatus(status_raw)
            except ValueError:
                status = ClientSupplierStatus.ACTIVE
            out.append(
                ClientSupplier(
                    id=row.id,
                    client_id=row.client_id,
                    name=row.name or "",
                    status=status,
                    created_at=_ensure_utc(row.created_at) or now_utc(),
                    updated_at=_ensure_utc(row.updated_at) or now_utc(),
                )
            )
        return out

