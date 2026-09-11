"""Migration 0110 — import lease / recovery columns."""

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
        / "0110_import_materialization_lease_recovery.sql"
    ).read_text(encoding="utf-8")


def test_migration_0110_adds_lease_and_review() -> None:
    text = _migration_text()
    assert "materialization_owner" in text
    assert "materialization_lease_expires_at" in text
    assert "fencing_version" in text
    assert "REQUIRES_REVIEW" in text
    assert "IX_local_csv_imports_recovery" in text
    assert "CK_local_csv_imports_lease_owner_pair" in text


@pytest.mark.integration
def test_migration_0110_executes_idempotently() -> None:
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
              COL_LENGTH(N'dbo.local_csv_imports', N'materialization_owner'),
              COL_LENGTH(N'dbo.local_csv_imports', N'materialization_lease_expires_at'),
              COL_LENGTH(N'dbo.local_csv_imports', N'fencing_version'),
              (SELECT COUNT(*) FROM sys.indexes
               WHERE object_id = OBJECT_ID(N'dbo.local_csv_imports')
                 AND name = N'IX_local_csv_imports_recovery')
            """
        )
        row = cursor.fetchone()
    assert row[0] is not None
    assert row[1] is not None
    assert row[2] is not None
    assert int(row[3]) == 1
