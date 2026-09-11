"""Static contract checks for migration 0105."""

from pathlib import Path

import pytest

from src.database.migrations import service as migration_service
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
        / "0105_position_auto_materialization.sql"
    ).read_text(encoding="utf-8")


def _down_migration_text() -> str:
    return (
        Path(__file__).resolve().parents[2]
        / "src"
        / "database"
        / "migrations"
        / "versions"
        / "0105_position_auto_materialization.down.sql"
    ).read_text(encoding="utf-8")


def test_migration_adds_location_provenance_without_replacing_canonical_storage() -> None:
    text = _migration_text()

    assert "ALTER TABLE dbo.aisle_locations" in text
    assert "raw_recognition_code NVARCHAR(4000)" in text
    assert "creation_source" in text
    assert "auto_materialized_at" in text
    assert "CREATE TABLE dbo.position_materialization_requests" in text
    assert "idempotency_key VARCHAR(128)" in text
    assert "request_hash CHAR(64)" in text
    assert "normalized_code NVARCHAR(64)" in text
    assert "UQ_pmr_client_idempotency_key" in text
    assert "association_status" in text
    assert "CK_pmr_association_state" in text
    assert "position_created BIT NULL" in text
    assert "position_idempotent_replay BIT NULL" in text
    assert "position_materialization_request_id VARCHAR(36) NULL" in text

    assert "CREATE TABLE dbo.positions" not in text
    assert "client_position_labels" not in text
    assert "CREATE UNIQUE NONCLUSTERED INDEX UQ_aisle_locations" in text
    assert "UPDATE dbo.aisle_locations\nSET normalized_code" not in text


def test_migration_has_duplicate_preflight_and_historical_manual_default() -> None:
    text = _migration_text()

    preflight = text.index("duplicate_count")
    ledger_unique = text.index("CREATE UNIQUE NONCLUSTERED INDEX UQ_pmr")
    assert preflight < ledger_unique
    assert "SET creation_source = 'MANUAL'" in text
    assert "DEFAULT ('MANUAL')" in text
    assert "IF COL_LENGTH" in text
    assert "Malformed active canonical position identity index" in text
    assert "Duplicate active canonical position identities detected" in text
    assert "Malformed position materialization ledger unique index" in text
    assert "i.is_unique = 1 AND i.is_disabled = 0" in text
    assert "ic.key_ordinal = 3 AND c.name = N'normalized_code'" in text


def test_down_migration_is_fail_closed_and_preserves_conditionally_owned_columns() -> None:
    text = _down_migration_text()

    assert "POSITION_AUTO_MATERIALIZATION_ENABLED" in text
    assert "POSITION_MATERIALIZATION_RECOVERY_ENABLED" in text
    assert "take a database backup" in text
    assert "THROW 51014" in text
    assert "THROW 51015" in text
    assert "THROW 51017" in text
    assert "THROW 51018" in text
    assert "There is no operator override" in text
    assert "DROP TABLE dbo.position_materialization_requests" in text
    assert "DELETE FROM dbo.aisle_locations" not in text
    assert "DELETE FROM dbo.mobile_preliminary_detections" not in text
    assert "DROP COLUMN creation_source" not in text
    assert "DROP COLUMN position_materialization_request_id" not in text


@pytest.mark.integration
def test_migration_0105_executes_idempotently_on_configured_sql_server() -> None:
    client = sql_server_client_or_skip(resolved_sqlserver_connection_string_for_tests())
    ensure_sql_migrations_applied(client)
    batches = migration_service._split_sql_batches(_migration_text())

    for _ in range(2):
        for statement in batches:
            with client.cursor() as cursor:
                cursor.execute(statement)

    with client.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                COL_LENGTH(N'dbo.aisle_locations', N'auto_materialized_at') AS provenance_column,
                OBJECT_ID(N'dbo.position_materialization_requests', N'U') AS ledger_table,
                INDEXPROPERTY(
                    OBJECT_ID(N'dbo.position_materialization_requests'),
                    N'UQ_pmr_client_idempotency_key',
                    N'IsUnique'
                ) AS ledger_unique,
                COL_LENGTH(
                    N'dbo.mobile_preliminary_detections',
                    N'position_idempotent_replay'
                ) AS replay_column,
                COL_LENGTH(
                    N'dbo.mobile_preliminary_detections',
                    N'position_materialization_request_id'
                ) AS request_column
            """
        )
        row = cursor.fetchone()

    assert row.provenance_column is not None
    assert row.ledger_table is not None
    assert int(row.ledger_unique) == 1
    assert row.replay_column is not None
    assert row.request_column is not None
