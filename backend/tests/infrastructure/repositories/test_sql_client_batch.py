"""Unit tests for SqlClientRepository.get_by_ids (no live DB)."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from src.infrastructure.repositories.sql_client_repository import SqlClientRepository


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


class RecordingClient:
    def __init__(self, rows: list | None = None) -> None:
        self.cursor_instance = RecordingCursor(rows)

    def cursor(self) -> RecordingCursor:
        return self.cursor_instance


def test_client_get_by_ids_empty_zero_queries() -> None:
    client = RecordingClient()
    repo = SqlClientRepository(client)  # type: ignore[arg-type]
    assert repo.get_by_ids([]) == {}
    assert client.cursor_instance.executions == []


def test_client_get_by_ids_one_query_dedupes() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    rows = [
        SimpleNamespace(
            id="c1",
            name="Cliente",
            status="active",
            created_at=now,
            updated_at=now,
            default_identification_mode=None,
        )
    ]
    client = RecordingClient(rows)
    repo = SqlClientRepository(client)  # type: ignore[arg-type]
    result = repo.get_by_ids(["c1", "c1", ""])
    assert len(client.cursor_instance.executions) == 1
    sql, params = client.cursor_instance.executions[0]
    assert "id IN (" in sql
    assert "c1" not in sql
    assert params == ("c1",)
    assert result["c1"].name == "Cliente"
