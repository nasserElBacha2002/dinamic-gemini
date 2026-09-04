"""SQL Server ClientSupplierLabelProfile repository (Phase 1)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone

import pyodbc

from src.application.ports.client_supplier_label_profile_repository import (
    ClientSupplierLabelProfileRepository,
)
from src.database.sqlserver import SqlServerClient
from src.domain.label_profiles.entities import ClientSupplierLabelProfile
from src.domain.label_profiles.kinds import LabelKind, LabelProfileSource, parse_label_kind
from src.infrastructure.database.sql_transaction import sql_repository_cursor


def _to_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _row_to_profile(row) -> ClientSupplierLabelProfile:
    return ClientSupplierLabelProfile(
        id=str(row.id),
        client_supplier_id=str(row.client_supplier_id),
        label_kind=parse_label_kind(str(row.label_kind)),
        source=LabelProfileSource(str(row.source).strip().upper()),
        created_at=_to_utc(row.created_at),
        updated_at=_to_utc(row.updated_at),
    )


def _is_cslp_unique_violation(exc: pyodbc.IntegrityError) -> bool:
    msg = str(exc).lower()
    return "unique" in msg or "2627" in msg or "2601" in msg


class SqlClientSupplierLabelProfileRepository(ClientSupplierLabelProfileRepository):
    def __init__(self, client: SqlServerClient, *, connection: object | None = None) -> None:
        self._client = client
        self._connection = connection

    def upsert(self, profile: ClientSupplierLabelProfile) -> ClientSupplierLabelProfile:
        created = _to_utc(profile.created_at) or datetime.now(timezone.utc)
        updated = _to_utc(profile.updated_at) or created
        last_exc: pyodbc.IntegrityError | None = None
        for _ in range(3):
            try:
                with sql_repository_cursor(self._client, connection=self._connection) as cur:
                    cur.execute(
                        """
                        UPDATE client_supplier_label_profiles
                        SET source = ?, updated_at = ?
                        WHERE client_supplier_id = ? AND label_kind = ?
                        """,
                        (
                            profile.source.value,
                            updated,
                            profile.client_supplier_id,
                            profile.label_kind.value,
                        ),
                    )
                    if cur.rowcount == 0:
                        cur.execute(
                            """
                            INSERT INTO client_supplier_label_profiles (
                                id, client_supplier_id, label_kind, source, created_at, updated_at
                            ) VALUES (?, ?, ?, ?, ?, ?)
                            """,
                            (
                                profile.id,
                                profile.client_supplier_id,
                                profile.label_kind.value,
                                profile.source.value,
                                created,
                                updated,
                            ),
                        )
                return profile
            except pyodbc.IntegrityError as exc:
                if not _is_cslp_unique_violation(exc):
                    raise
                last_exc = exc
                existing = self.get_by_supplier_and_kind(
                    profile.client_supplier_id, profile.label_kind
                )
                if existing is not None:
                    profile = ClientSupplierLabelProfile(
                        id=existing.id,
                        client_supplier_id=profile.client_supplier_id,
                        label_kind=profile.label_kind,
                        source=profile.source,
                        created_at=existing.created_at,
                        updated_at=updated,
                    )
        if last_exc is not None:
            raise last_exc
        return profile

    def get_by_supplier_and_kind(
        self, client_supplier_id: str, label_kind: LabelKind
    ) -> ClientSupplierLabelProfile | None:
        with sql_repository_cursor(self._client, connection=self._connection) as cur:
            cur.execute(
                """
                SELECT id, client_supplier_id, label_kind, source, created_at, updated_at
                FROM client_supplier_label_profiles
                WHERE client_supplier_id = ? AND label_kind = ?
                """,
                (client_supplier_id, label_kind.value),
            )
            row = cur.fetchone()
        return _row_to_profile(row) if row else None

    def list_by_supplier(
        self, client_supplier_id: str
    ) -> Sequence[ClientSupplierLabelProfile]:
        with sql_repository_cursor(self._client, connection=self._connection) as cur:
            cur.execute(
                """
                SELECT id, client_supplier_id, label_kind, source, created_at, updated_at
                FROM client_supplier_label_profiles
                WHERE client_supplier_id = ?
                ORDER BY label_kind
                """,
                (client_supplier_id,),
            )
            rows = cur.fetchall()
        return [_row_to_profile(row) for row in rows]

    def delete_by_supplier_and_kind(
        self, client_supplier_id: str, label_kind: LabelKind
    ) -> None:
        with sql_repository_cursor(self._client, connection=self._connection) as cur:
            cur.execute(
                """
                DELETE FROM client_supplier_label_profiles
                WHERE client_supplier_id = ? AND label_kind = ?
                """,
                (client_supplier_id, label_kind.value),
            )
