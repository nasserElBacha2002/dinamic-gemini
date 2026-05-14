"""Unit tests for :mod:`src.runtime.container.repository_builders` wiring contract."""

from __future__ import annotations

from collections.abc import Callable

from src.database.sqlserver import SqlServerClient
from src.runtime.container.repository_builders import build_inventory_repository


def test_build_inventory_repository_forwards_backend_identifiers_to_build_repo() -> None:
    calls: list[tuple[str, str]] = []

    def recording_build_repo(
        *,
        backend_info_name: str,
        sql_error_subject: str,
        build_sql: Callable[[SqlServerClient], object],
        build_memory: Callable[[], object],
    ) -> str:
        calls.append((backend_info_name, sql_error_subject))
        return build_memory()

    result = build_inventory_repository(recording_build_repo)  # type: ignore[arg-type]
    assert result is not None
    assert calls == [("InventoryRepository", "repo")]
