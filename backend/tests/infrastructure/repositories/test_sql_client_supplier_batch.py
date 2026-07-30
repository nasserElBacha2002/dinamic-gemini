"""Unit tests for SqlClientSupplierRepository batch + mapping (no live DB)."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from src.application.errors import RepositoryRowMappingError
from src.infrastructure.repositories.sql_client_supplier_repository import (
    SqlClientSupplierRepository,
    _supplier_from_row,
)


class RecordingCursor:
    def __init__(self, rows: list | None = None) -> None:
        self.executions: list[tuple[str, tuple]] = []
        self._rows = rows or []

    def __enter__(self) -> RecordingCursor:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def execute(self, sql: str, params: tuple = ()) -> None:
        self.executions.append((sql, params))

    def fetchall(self) -> list:
        return list(self._rows)

    def fetchone(self) -> object | None:
        return self._rows[0] if self._rows else None


class RecordingClient:
    def __init__(self, rows: list | None = None) -> None:
        self.cursor_instance = RecordingCursor(rows)

    def cursor(self) -> RecordingCursor:
        return self.cursor_instance


def _row(
    *,
    supplier_id: str = "sup-1",
    client_id: str = "client-1",
    name: str = "Acme",
    status: str = "active",
    created_at: datetime | None = None,
    updated_at: datetime | None = None,
) -> SimpleNamespace:
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    return SimpleNamespace(
        id=supplier_id,
        client_id=client_id,
        name=name,
        status=status,
        created_at=created_at if created_at is not None else now,
        updated_at=updated_at if updated_at is not None else now,
    )


def test_get_by_client_and_ids_empty_input_zero_queries() -> None:
    client = RecordingClient()
    repo = SqlClientSupplierRepository(client)  # type: ignore[arg-type]
    assert repo.get_by_client_and_ids("client-1", []) == {}
    assert client.cursor_instance.executions == []


def test_get_by_client_and_ids_empty_client_zero_queries() -> None:
    client = RecordingClient()
    repo = SqlClientSupplierRepository(client)  # type: ignore[arg-type]
    assert repo.get_by_client_and_ids("", ["sup-1"]) == {}
    assert client.cursor_instance.executions == []


def test_get_by_client_and_ids_one_query_dedupes_and_scopes() -> None:
    rows = [_row(supplier_id="sup-1"), _row(supplier_id="sup-2", name="Beta")]
    client = RecordingClient(rows)
    repo = SqlClientSupplierRepository(client)  # type: ignore[arg-type]
    result = repo.get_by_client_and_ids("client-1", ["sup-1", "sup-1", "sup-2", ""])
    assert len(client.cursor_instance.executions) == 1
    sql, params = client.cursor_instance.executions[0]
    assert "client_id = ?" in sql
    assert "id IN (" in sql
    assert "?" in sql
    assert "sup-1" not in sql  # values must be parameterized
    assert params[0] == "client-1"
    assert set(params[1:]) == {"sup-1", "sup-2"}
    assert set(result) == {"sup-1", "sup-2"}
    assert result["sup-1"].name == "Acme"


def test_get_by_ids_empty_zero_queries() -> None:
    client = RecordingClient()
    repo = SqlClientSupplierRepository(client)  # type: ignore[arg-type]
    assert repo.get_by_ids([]) == {}
    assert client.cursor_instance.executions == []


def test_get_by_ids_one_query_partial() -> None:
    client = RecordingClient([_row(supplier_id="sup-1")])
    repo = SqlClientSupplierRepository(client)  # type: ignore[arg-type]
    result = repo.get_by_ids(["sup-1", "missing"])
    assert len(client.cursor_instance.executions) == 1
    assert "sup-1" in result
    assert "missing" not in result


def test_supplier_from_row_rejects_invalid_status() -> None:
    with pytest.raises(RepositoryRowMappingError, match="invalid status"):
        _supplier_from_row(_row(status="not-a-status"))


def test_supplier_from_row_rejects_null_timestamps() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    with pytest.raises(RepositoryRowMappingError, match="timestamps"):
        _supplier_from_row(
            SimpleNamespace(
                id="sup-1",
                client_id="client-1",
                name="Acme",
                status="active",
                created_at=None,
                updated_at=now,
            )
        )
