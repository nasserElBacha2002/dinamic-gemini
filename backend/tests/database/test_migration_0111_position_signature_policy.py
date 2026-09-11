"""Migration 0111 — signature_policy + position_flexible_capabilities."""

from pathlib import Path

import pytest

from src.database.migrations import service as migration_service
from tests.support.sql_integration import sql_server_client_or_skip
from tests.support.sql_migration_fixture import ensure_sql_migrations_applied
from tests.support.sqlserver_test_connection import resolved_sqlserver_connection_string_for_tests

MIGRATIONS = (
    Path(__file__).resolve().parents[2] / "src/database/migrations/versions"
)


def _migration_text() -> str:
    return (
        MIGRATIONS / "0111_position_signature_policy_and_capabilities.sql"
    ).read_text(encoding="utf-8")


def test_migration_0111_adds_signature_policy_and_capabilities() -> None:
    text = _migration_text()
    assert "signature_policy NVARCHAR(32) NOT NULL" in text
    assert "CK_cslp_signature_policy" in text
    assert "CK_sep_signature_policy" in text
    assert "REQUIRED" in text
    assert "OPTIONAL" in text
    assert "NOT_APPLICABLE" in text
    assert "CREATE TABLE dbo.position_flexible_capabilities" in text
    assert "SHADOW" in text
    assert "ENFORCED" in text
    assert "UQ_pfc_scope_key" in text
    assert "ISNULL(client_supplier_id" in text
    assert "ISNULL(profile_id" in text


def test_migration_0111_capabilities_table_shape() -> None:
    text = _migration_text()
    for column in (
        "id",
        "client_id",
        "client_supplier_id",
        "profile_id",
        "channel",
        "mode",
        "enabled",
        "reason",
        "created_by",
        "created_at",
        "updated_at",
        "scope_key",
    ):
        assert column in text
    assert "FK_pfc_client" in text
    assert "CK_pfc_channel" in text
    assert "CK_pfc_mode" in text


@pytest.mark.integration
def test_migration_0111_executes_idempotently() -> None:
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
              COL_LENGTH(N'dbo.client_supplier_label_profiles', N'signature_policy'),
              COL_LENGTH(N'dbo.supplier_extraction_profiles', N'signature_policy'),
              OBJECT_ID(N'dbo.position_flexible_capabilities', N'U'),
              (SELECT COUNT(*) FROM sys.indexes
               WHERE object_id = OBJECT_ID(N'dbo.position_flexible_capabilities')
                 AND name = N'UQ_pfc_scope_key'
                 AND is_unique = 1)
            """
        )
        row = cursor.fetchone()
    assert row[0] is not None
    assert row[1] is not None
    assert row[2] is not None
    assert int(row[3]) == 1
