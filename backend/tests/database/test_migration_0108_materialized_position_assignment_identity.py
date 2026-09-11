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
        / "0108_materialized_position_assignment_identity.sql"
    ).read_text(encoding="utf-8")


def test_migration_is_additive_guarded_and_indexed() -> None:
    text = _migration_text()
    assert "ADD aisle_location_id VARCHAR(36) NULL" in text
    assert "ADD source_detection_id VARCHAR(36) NULL" in text
    assert "FK_ppa_aisle_location" in text
    assert "FK_pmar_source_detection" in text
    assert "ON DELETE SET NULL" in text
    assert "FK_ppa_detection" not in text
    assert "DROP CONSTRAINT CK_ppa_automatic_evidence" in text
    assert "source_detection_id IS NOT NULL" in text
    assert "position_label_id IS NOT NULL OR aisle_location_id IS NOT NULL" in text
    assert "position_label_id IS NULL AND aisle_location_id IS NULL" in text
    assert text.count("WITH CHECK") >= 4
    assert "CREATE UNIQUE NONCLUSTERED INDEX UQ_pmar_source_detection" in text
    assert "WHERE source_detection_id IS NOT NULL" in text
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
              COL_LENGTH(N'dbo.product_position_assignments', N'aisle_location_id'),
              COL_LENGTH(
                N'dbo.position_materialization_association_receipts',
                N'source_detection_id'
              ),
              (SELECT COUNT(*) FROM sys.foreign_keys
               WHERE name IN (N'FK_ppa_aisle_location', N'FK_pmar_source_detection')),
              (SELECT COUNT(*) FROM sys.indexes
               WHERE object_id = OBJECT_ID(
                 N'dbo.position_materialization_association_receipts'
               ) AND name = N'UQ_pmar_source_detection'
                 AND is_unique = 1 AND has_filter = 1),
              (SELECT delete_referential_action FROM sys.foreign_keys
               WHERE parent_object_id = OBJECT_ID(
                 N'dbo.position_materialization_association_receipts'
               ) AND name = N'FK_pmar_source_detection')
            """
        )
        row = cursor.fetchone()
    assert row[0] is not None
    assert row[1] is not None
    assert int(row[2]) == 2
    assert int(row[3]) == 1
    assert int(row[4]) == 2


def test_down_restores_0083_constraints_before_dropping_column() -> None:
    down = (
        Path(__file__).resolve().parents[2]
        / "src/database/migrations/versions"
        / "0108_materialized_position_assignment_identity.down.sql"
    ).read_text(encoding="utf-8")
    assert "WHERE aisle_location_id IS NOT NULL" in down
    assert "position_label_id IS NOT NULL AND source_detection_id IS NOT NULL" in down
    assert "assignment_status = 'ASSIGNED_AUTOMATIC' OR position_label_id IS NULL" in down
    assert down.index("ADD CONSTRAINT CK_ppa_automatic_evidence") < down.index(
        "DROP COLUMN aisle_location_id"
    )
