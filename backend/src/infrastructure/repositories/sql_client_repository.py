"""SQL Server implementation of ClientRepository — Phase A1 foundation."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone

from src.application.ports.repositories import ClientRepository
from src.database.sqlserver import SqlServerClient, now_utc
from src.domain.aisle_identification.modes import optional_config_identification_mode
from src.domain.client.entities import Client, ClientStatus


def _ensure_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt
    return dt.replace(tzinfo=timezone.utc)


def _client_from_row(row) -> Client:
    status_raw = str(getattr(row, "status", ClientStatus.ACTIVE.value) or ClientStatus.ACTIVE.value)
    try:
        status = ClientStatus(status_raw)
    except ValueError:
        status = ClientStatus.ACTIVE
    return Client(
        id=row.id,
        name=row.name or "",
        status=status,
        created_at=_ensure_utc(row.created_at) or now_utc(),
        updated_at=_ensure_utc(row.updated_at) or now_utc(),
        default_identification_mode=optional_config_identification_mode(
            getattr(row, "default_identification_mode", None)
        ),
    )


class SqlClientRepository(ClientRepository):
    def __init__(self, client: SqlServerClient) -> None:
        self._client = client

    def save(self, client: Client) -> None:
        created = _ensure_utc(client.created_at)
        updated = _ensure_utc(client.updated_at)
        mode_val = (
            client.default_identification_mode.value
            if client.default_identification_mode is not None
            else None
        )
        with self._client.cursor() as cur:
            cur.execute(
                """
                UPDATE clients
                SET name = ?, status = ?, updated_at = ?, default_identification_mode = ?
                WHERE id = ?
                """,
                (client.name, client.status.value, updated, mode_val, client.id),
            )
            if cur.rowcount == 0:
                cur.execute(
                    """
                    INSERT INTO clients (
                        id, name, status, created_at, updated_at, default_identification_mode
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (client.id, client.name, client.status.value, created, updated, mode_val),
                )

    def get_by_id(self, client_id: str) -> Client | None:
        with self._client.cursor() as cur:
            cur.execute(
                """
                SELECT id, name, status, created_at, updated_at, default_identification_mode
                FROM clients
                WHERE id = ?
                """,
                (client_id,),
            )
            row = cur.fetchone()
        if not row:
            return None
        return _client_from_row(row)

    def list_all(self) -> Sequence[Client]:
        with self._client.cursor() as cur:
            cur.execute(
                """
                SELECT id, name, status, created_at, updated_at, default_identification_mode
                FROM clients
                ORDER BY created_at DESC
                """
            )
            rows = cur.fetchall()
        return [_client_from_row(row) for row in rows]

