"""SQL Server implementation of ClientSupplierRepository — Phase A2 foundation."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone

from src.application.errors import RepositoryRowMappingError
from src.application.ports.repositories import ClientSupplierRepository
from src.database.sqlserver import SqlServerClient
from src.domain.client_supplier.entities import ClientSupplier, ClientSupplierStatus


def _ensure_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt
    return dt.replace(tzinfo=timezone.utc)


def _supplier_from_row(row: object) -> ClientSupplier:
    supplier_id = getattr(row, "id", None)
    status_raw = getattr(row, "status", None)
    if status_raw is None or str(status_raw).strip() == "":
        raise RepositoryRowMappingError(
            f"client_suppliers row missing status id={supplier_id!r}"
        )
    try:
        status = ClientSupplierStatus(str(status_raw))
    except ValueError as exc:
        raise RepositoryRowMappingError(
            f"client_suppliers invalid status={status_raw!r} id={supplier_id!r}"
        ) from exc
    created = _ensure_utc(getattr(row, "created_at", None))
    updated = _ensure_utc(getattr(row, "updated_at", None))
    if created is None or updated is None:
        raise RepositoryRowMappingError(
            f"client_suppliers row missing required timestamps id={supplier_id!r}"
        )
    return ClientSupplier(
        id=str(supplier_id),
        client_id=str(getattr(row, "client_id")),
        name=str(getattr(row, "name", None) or ""),
        status=status,
        created_at=created,
        updated_at=updated,
    )


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
        return _supplier_from_row(row)

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
        return _supplier_from_row(row)

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
        return [_supplier_from_row(row) for row in rows]

    def get_by_ids(self, supplier_ids: Sequence[str]) -> dict[str, ClientSupplier]:
        uniq = list({sid for sid in supplier_ids if sid})
        if not uniq:
            return {}
        placeholders = ",".join("?" * len(uniq))
        with self._client.cursor() as cur:
            cur.execute(
                f"""
                SELECT id, client_id, name, status, created_at, updated_at
                FROM client_suppliers
                WHERE id IN ({placeholders})
                """,
                tuple(uniq),
            )
            rows = cur.fetchall()
        return {row.id: _supplier_from_row(row) for row in rows}

    def get_by_client_and_ids(
        self, client_id: str, supplier_ids: Sequence[str]
    ) -> dict[str, ClientSupplier]:
        uniq = list({sid for sid in supplier_ids if sid})
        if not uniq or not client_id:
            return {}
        placeholders = ",".join("?" * len(uniq))
        with self._client.cursor() as cur:
            cur.execute(
                f"""
                SELECT id, client_id, name, status, created_at, updated_at
                FROM client_suppliers
                WHERE client_id = ?
                  AND id IN ({placeholders})
                """,
                (client_id, *uniq),
            )
            rows = cur.fetchall()
        return {row.id: _supplier_from_row(row) for row in rows}
