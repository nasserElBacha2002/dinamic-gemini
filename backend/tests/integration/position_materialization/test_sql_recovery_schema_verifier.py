from __future__ import annotations

from pathlib import Path

import pytest

from src.database.migrations import service as migration_service
from src.infrastructure.persistence.position_materialization_schema_verifier import (
    SCHEMA_PRECONDITION_ERROR,
    PositionMaterializationSchemaError,
    SqlPositionMaterializationSchemaVerifier,
)
from tests.support.sql_integration import sql_server_client_or_skip
from tests.support.sql_migration_fixture import ensure_sql_migrations_applied
from tests.support.sqlserver_test_connection import (
    resolved_sqlserver_connection_string_for_tests,
)

pytestmark = pytest.mark.integration

MIGRATIONS = (
    Path(__file__).parents[3]
    / "src/database/migrations/versions/0106_position_materialization_association_recovery.sql",
    Path(__file__).parents[3]
    / "src/database/migrations/versions/0108_materialized_position_assignment_identity.sql",
)


def _restore_schema(client) -> None:
    for migration in MIGRATIONS:
        for statement in migration_service._split_sql_batches(
            migration.read_text(encoding="utf-8")
        ):
            with client.cursor() as cursor:
                cursor.execute(statement)


def test_recovery_schema_verifier_fails_for_malformed_and_missing_schema() -> None:
    client = sql_server_client_or_skip(resolved_sqlserver_connection_string_for_tests())
    ensure_sql_migrations_applied(client)
    verifier = SqlPositionMaterializationSchemaVerifier(client)
    verifier.verify()

    try:
        with client.cursor() as cursor:
            cursor.execute(
                """
                ALTER INDEX IX_pmr_association_due
                ON dbo.position_materialization_requests DISABLE
                """
            )
        with pytest.raises(PositionMaterializationSchemaError) as malformed:
            verifier.verify()
        assert str(malformed.value) == SCHEMA_PRECONDITION_ERROR

        with client.cursor() as cursor:
            cursor.execute(
                """
                ALTER INDEX IX_pmr_association_due
                ON dbo.position_materialization_requests REBUILD
                """
            )
            cursor.execute("DROP TABLE dbo.position_materialization_association_receipts")
        with pytest.raises(PositionMaterializationSchemaError) as missing:
            verifier.verify()
        assert str(missing.value) == SCHEMA_PRECONDITION_ERROR
    finally:
        _restore_schema(client)

    verifier.verify()
