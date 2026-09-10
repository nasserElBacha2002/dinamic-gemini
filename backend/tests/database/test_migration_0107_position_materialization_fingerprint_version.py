from pathlib import Path

import pytest

from src.database.migrations import service as migration_service
from src.infrastructure.persistence.position_materialization_schema_verifier import (
    PositionMaterializationSchemaError,
    SqlPositionMaterializationSchemaVerifier,
)
from tests.support.sql_integration import sql_server_client_or_skip
from tests.support.sql_migration_fixture import ensure_sql_migrations_applied
from tests.support.sqlserver_test_connection import resolved_sqlserver_connection_string_for_tests


def _migration_text() -> str:
    return (
        Path(__file__).resolve().parents[2]
        / "src"
        / "database"
        / "migrations"
        / "versions"
        / "0107_position_materialization_fingerprint_version.sql"
    ).read_text(encoding="utf-8")


def _run_sql(client, sql: str) -> None:
    for statement in migration_service._split_sql_batches(sql):
        with client.cursor() as cursor:
            cursor.execute(statement)


def test_migration_is_additive_and_backfills_v1() -> None:
    text = _migration_text()

    assert "fingerprint_version INT NOT NULL" in text
    assert "DEFAULT (1) WITH VALUES" in text
    assert "CHECK (fingerprint_version = 1)" in text
    assert "DROP COLUMN" not in text


def test_down_migration_fails_closed_before_dropping_metadata() -> None:
    down = (
        Path(__file__).resolve().parents[2]
        / "src/database/migrations/versions"
        / "0107_position_materialization_fingerprint_version.down.sql"
    ).read_text(encoding="utf-8")

    assert "fingerprint_version <> 1" in down
    assert "THROW 51018" in down
    assert down.index("THROW 51018") < down.index("DROP CONSTRAINT")


@pytest.mark.integration
def test_migration_0107_executes_idempotently_on_configured_sql_server() -> None:
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
                COL_LENGTH(
                    N'dbo.position_materialization_requests',
                    N'fingerprint_version'
                ) AS fingerprint_version_column,
                (SELECT COUNT_BIG(*)
                 FROM dbo.position_materialization_requests
                 WHERE fingerprint_version <> 1) AS non_v1_rows
            """
        )
        row = cursor.fetchone()

    assert row.fingerprint_version_column is not None
    assert int(row.non_v1_rows) == 0


@pytest.mark.integration
@pytest.mark.parametrize(
    "malformation_sql",
    [
        """
        ALTER TABLE dbo.position_materialization_requests
            DROP CONSTRAINT CK_pmr_fingerprint_version;
        ALTER TABLE dbo.position_materialization_requests
            DROP CONSTRAINT DF_pmr_fingerprint_version;
        ALTER TABLE dbo.position_materialization_requests
            ALTER COLUMN fingerprint_version INT NULL;
        ALTER TABLE dbo.position_materialization_requests
            ADD CONSTRAINT DF_pmr_fingerprint_version
                DEFAULT (1) FOR fingerprint_version;
        ALTER TABLE dbo.position_materialization_requests WITH CHECK
            ADD CONSTRAINT CK_pmr_fingerprint_version
                CHECK (fingerprint_version = 1);
        """,
        """
        ALTER TABLE dbo.position_materialization_requests
            DROP CONSTRAINT CK_pmr_fingerprint_version;
        ALTER TABLE dbo.position_materialization_requests
            DROP CONSTRAINT DF_pmr_fingerprint_version;
        ALTER TABLE dbo.position_materialization_requests
            ALTER COLUMN fingerprint_version SMALLINT NOT NULL;
        ALTER TABLE dbo.position_materialization_requests
            ADD CONSTRAINT DF_pmr_fingerprint_version
                DEFAULT (1) FOR fingerprint_version;
        ALTER TABLE dbo.position_materialization_requests WITH CHECK
            ADD CONSTRAINT CK_pmr_fingerprint_version
                CHECK (fingerprint_version = 1);
        """,
        """
        ALTER TABLE dbo.position_materialization_requests
            DROP CONSTRAINT DF_pmr_fingerprint_version;
        ALTER TABLE dbo.position_materialization_requests
            ADD CONSTRAINT DF_pmr_fingerprint_version
                DEFAULT (2) FOR fingerprint_version;
        """,
        """
        ALTER TABLE dbo.position_materialization_requests
            DROP CONSTRAINT CK_pmr_fingerprint_version;
        ALTER TABLE dbo.position_materialization_requests
            ADD CONSTRAINT CK_pmr_fingerprint_version
                CHECK (fingerprint_version > 0);
        """,
        """
        ALTER TABLE dbo.position_materialization_requests
            NOCHECK CONSTRAINT CK_pmr_fingerprint_version;
        """,
    ],
)
def test_verifier_rejects_malformed_fingerprint_schema(malformation_sql: str) -> None:
    client = sql_server_client_or_skip(resolved_sqlserver_connection_string_for_tests())
    ensure_sql_migrations_applied(client)
    try:
        _run_sql(client, malformation_sql)
        with pytest.raises(PositionMaterializationSchemaError):
            SqlPositionMaterializationSchemaVerifier(client).verify()
    finally:
        _run_sql(client, _migration_text())
        SqlPositionMaterializationSchemaVerifier(client).verify()
