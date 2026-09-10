from __future__ import annotations

from pathlib import Path

import pytest

from src.database.migrations import service as migration_service
from src.infrastructure.persistence.position_materialization_schema_verifier import (
    PositionMaterializationSchemaError,
    SqlPositionMaterializationSchemaVerifier,
)
from tests.support.sql_integration import sql_server_client_or_skip
from tests.support.sql_migration_fixture import ensure_sql_migrations_applied
from tests.support.sqlserver_test_connection import (
    resolved_sqlserver_connection_string_for_tests,
)

MIGRATIONS = Path(__file__).parents[2] / "src/database/migrations/versions"


def test_0106_is_idempotent_additive_and_claim_ready() -> None:
    text = (MIGRATIONS / "0106_position_materialization_association_recovery.sql").read_text(
        encoding="utf-8"
    )

    assert "COL_LENGTH" in text
    assert "attempt_count >= 0" in text
    assert "CK_pmr_lease_pair" in text
    assert "'EXHAUSTED'" in text
    assert "position_materialization_association_receipts" in text
    assert "FOREIGN KEY (request_id)" in text
    assert "IX_pmr_association_due" in text


def test_0106_down_requires_unconditional_drain() -> None:
    text = (MIGRATIONS / "0106_position_materialization_association_recovery.down.sql").read_text(
        encoding="utf-8"
    )

    assert "there is deliberately no override" in text
    assert "SESSION_CONTEXT" not in text
    assert "'PENDING', 'REQUIRES_REVIEW', 'EXHAUSTED'" in text
    assert "lease_owner IS NOT NULL" in text
    assert "lease_expires_at IS NOT NULL" in text
    assert "THROW 51016" in text
    assert "permanently lost" in text
    assert "SET association_status = 'REQUIRES_REVIEW'" not in text


@pytest.mark.integration
def test_migration_0106_executes_idempotently_on_configured_sql_server() -> None:
    client = sql_server_client_or_skip(resolved_sqlserver_connection_string_for_tests())
    ensure_sql_migrations_applied(client)
    text = (MIGRATIONS / "0106_position_materialization_association_recovery.sql").read_text(
        encoding="utf-8"
    )
    batches = migration_service._split_sql_batches(text)

    for _ in range(2):
        for statement in batches:
            with client.cursor() as cursor:
                cursor.execute(statement)

    with client.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                COL_LENGTH(
                    N'dbo.position_materialization_requests', N'attempt_count'
                ) AS attempt_column,
                OBJECT_ID(
                    N'dbo.position_materialization_association_receipts', N'U'
                ) AS receipt_table,
                INDEXPROPERTY(
                    OBJECT_ID(N'dbo.position_materialization_requests'),
                    N'IX_pmr_association_due',
                    N'IsUnique'
                ) AS due_index_is_unique
            """
        )
        row = cursor.fetchone()

    assert row.attempt_column is not None
    assert row.receipt_table is not None
    assert int(row.due_index_is_unique) == 0


@pytest.mark.integration
def test_0105_0106_0107_chain_applies_sequentially_and_idempotently() -> None:
    client = sql_server_client_or_skip(resolved_sqlserver_connection_string_for_tests())
    ensure_sql_migrations_applied(client)
    migration_paths = [
        MIGRATIONS / "0105_position_auto_materialization.sql",
        MIGRATIONS / "0106_position_materialization_association_recovery.sql",
        MIGRATIONS / "0107_position_materialization_fingerprint_version.sql",
    ]

    for _ in range(2):
        for path in migration_paths:
            for statement in migration_service._split_sql_batches(path.read_text(encoding="utf-8")):
                with client.cursor() as cursor:
                    cursor.execute(statement)

    SqlPositionMaterializationSchemaVerifier(client).verify()


@pytest.mark.integration
@pytest.mark.parametrize(
    ("malformation_sql", "restore_sql"),
    [
        (
            """
            ALTER TABLE dbo.position_materialization_association_receipts
                DROP CONSTRAINT CK_pmar_target_type;
            ALTER TABLE dbo.position_materialization_association_receipts
                ADD CONSTRAINT CK_pmar_target_type
                    CHECK (target_type IN ('IMAGE_RESULT', 'OTHER'));
            """,
            """
            ALTER TABLE dbo.position_materialization_association_receipts
                DROP CONSTRAINT CK_pmar_target_type;
            """,
        ),
        (
            """
            ALTER TABLE dbo.position_materialization_requests
                NOCHECK CONSTRAINT CK_pmr_lease_pair;
            """,
            """
            ALTER TABLE dbo.position_materialization_requests
                DROP CONSTRAINT CK_pmr_lease_pair;
            """,
        ),
    ],
)
def test_verifier_rejects_malformed_recovery_checks(
    malformation_sql: str,
    restore_sql: str,
) -> None:
    client = sql_server_client_or_skip(resolved_sqlserver_connection_string_for_tests())
    ensure_sql_migrations_applied(client)
    migration = (MIGRATIONS / "0106_position_materialization_association_recovery.sql").read_text(
        encoding="utf-8"
    )
    try:
        with client.cursor() as cursor:
            cursor.execute(malformation_sql)
        with pytest.raises(PositionMaterializationSchemaError):
            SqlPositionMaterializationSchemaVerifier(client).verify()
    finally:
        with client.cursor() as cursor:
            cursor.execute(restore_sql)
        for statement in migration_service._split_sql_batches(migration):
            with client.cursor() as cursor:
                cursor.execute(statement)
        SqlPositionMaterializationSchemaVerifier(client).verify()
