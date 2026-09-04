"""Integration upgrade test for migration 0100 label recognition profiles."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.database.sqlserver import SqlServerClient
from tests.support.sql_integration import sql_server_client_or_skip
from tests.support.sqlserver_test_connection import resolved_sqlserver_connection_string_for_tests

_MIGRATION_DIR = (
    Path(__file__).resolve().parents[2] / "src" / "database" / "migrations" / "versions"
)


def _read(name: str) -> str:
    return (_MIGRATION_DIR / name).read_text(encoding="utf-8")


def _apply_sql_batches(client: SqlServerClient, sql: str) -> None:
    batches: list[str] = []
    buf: list[str] = []
    for line in sql.splitlines():
        if line.strip().upper() == "GO":
            if buf:
                batches.append("\n".join(buf))
                buf = []
        else:
            buf.append(line)
    if buf:
        batches.append("\n".join(buf))
    with client.cursor() as cur:
        for batch in batches:
            if batch.strip():
                cur.execute(batch)


def test_migration_0100_files_exist_and_are_additive() -> None:
    up = _read("0100_label_recognition_profiles_phase1.sql")
    down = _read("0100_label_recognition_profiles_phase1.down.sql")
    assert "client_supplier_label_profiles" in up
    assert "CK_sep_label_kind" in up
    assert "CK_spc_label_kind" in up
    assert "CK_sri_label_kind" in up
    assert "DROP TABLE client_supplier_label_profiles" in down


@pytest.mark.integration
def test_migration_0100_upgrade_adds_columns_and_constraints() -> None:
    cs = resolved_sqlserver_connection_string_for_tests()
    if not cs:
        pytest.skip("SQL Server not configured")
    client = sql_server_client_or_skip(cs)
    _apply_sql_batches(client, _read("0100_label_recognition_profiles_phase1.sql"))

    with client.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*) AS n
            FROM sys.columns
            WHERE object_id = OBJECT_ID('supplier_extraction_profiles')
              AND name = 'label_kind'
            """
        )
        assert int(cur.fetchone().n) == 1

        cur.execute(
            """
            SELECT COUNT(*) AS n
            FROM sys.check_constraints
            WHERE name = 'CK_cslp_label_kind'
              AND parent_object_id = OBJECT_ID('client_supplier_label_profiles')
            """
        )
        assert int(cur.fetchone().n) == 1

        cur.execute(
            """
            SELECT COUNT(*) AS n
            FROM sys.tables
            WHERE name = 'client_supplier_label_profiles'
            """
        )
        assert int(cur.fetchone().n) == 1
