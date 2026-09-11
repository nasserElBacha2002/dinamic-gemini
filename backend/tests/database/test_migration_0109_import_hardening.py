"""Migration 0109 — import status machine + canonical length constraints."""

from pathlib import Path

import pytest

from src.database.migrations import service as migration_service
from tests.support.sql_integration import sql_server_client_or_skip
from tests.support.sql_migration_fixture import ensure_sql_migrations_applied
from tests.support.sqlserver_test_connection import resolved_sqlserver_connection_string_for_tests


def _migration_text() -> str:
    return (
        Path(__file__).resolve().parents[2]
        / "src/database/migrations/versions"
        / "0109_import_hardening_status_and_length.sql"
    ).read_text(encoding="utf-8")


def test_migration_expands_status_and_length_guards() -> None:
    text = _migration_text()
    assert "MATERIALIZING" in text
    assert "MATERIALIZATION_FAILED" in text
    assert "last_error_code" in text
    assert "materialization_attempts" in text
    assert "CK_local_csv_import_rows_position_code_len" in text
    assert "LEN(position_code) <= 64" in text
    assert "DROP COLUMN" not in text


@pytest.mark.integration
def test_migration_executes_idempotently_with_expected_contract() -> None:
    client = sql_server_client_or_skip(resolved_sqlserver_connection_string_for_tests())
    ensure_sql_migrations_applied(client)
    for _ in range(2):
        for statement in migration_service._split_sql_batches(_migration_text()):
            with client.cursor() as cursor:
                cursor.execute(statement)

    with client.cursor() as cursor:
        cursor.execute(
            """
            SELECT
              COL_LENGTH(N'dbo.local_csv_imports', N'last_error_code'),
              COL_LENGTH(N'dbo.local_csv_imports', N'materialization_attempts'),
              (SELECT definition FROM sys.check_constraints
               WHERE parent_object_id = OBJECT_ID(N'dbo.local_csv_imports')
                 AND name = N'CK_local_csv_imports_status'),
              (SELECT COUNT(*) FROM sys.check_constraints
               WHERE name = N'CK_local_csv_import_rows_position_code_len')
            """
        )
        row = cursor.fetchone()
    assert row[0] is not None
    assert row[1] is not None
    definition = str(row[2] or "")
    assert "MATERIALIZING" in definition
    assert "MATERIALIZATION_FAILED" in definition
    assert int(row[3]) == 1


def test_down_restores_previewed_confirmed_only() -> None:
    down = (
        Path(__file__).resolve().parents[2]
        / "src/database/migrations/versions"
        / "0109_import_hardening_status_and_length.down.sql"
    ).read_text(encoding="utf-8")
    assert "status IN (N'PREVIEWED', N'CONFIRMED')" in down
    assert "DROP COLUMN last_error_code" in down
