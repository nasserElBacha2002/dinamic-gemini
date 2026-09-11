"""Fail-closed Phase 4 import hardening preflight script checks."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.support.sql_integration import sql_server_client_or_skip
from tests.support.sql_migration_fixture import ensure_sql_migrations_applied
from tests.support.sqlserver_test_connection import resolved_sqlserver_connection_string_for_tests

ROOT = Path(__file__).resolve().parents[3]
PREFLIGHT = ROOT / "scripts" / "ops" / "phase-4-import-hardening-preflight.sql"


def test_preflight_script_exists_and_throws_on_errors() -> None:
    text = PREFLIGHT.read_text(encoding="utf-8")
    assert "THROW 51009" in text
    assert "MATERIALIZING_WITHOUT_LEASE" in text
    assert "PACKAGE_CSV_INCONSISTENT" in text
    assert "OVERSIZE_POSITION_CODE" in text
    assert "materialization_owner" in text
    assert "REQUIRES_REVIEW" in text
    assert "SET NOCOUNT OFF" in text


def test_preflight_keeps_diagnostic_selects() -> None:
    text = PREFLIGHT.read_text(encoding="utf-8")
    assert "SELECT status, COUNT(*) AS row_count" in text
    assert "SELECT code, detail FROM @errors" in text


@pytest.mark.integration
def test_preflight_passes_on_healthy_0110_sql_server() -> None:
    """Execute ops preflight against the configured test/dev SQL Server.

    Asserts live PASS (no THROW 51009) on a healthy migrated DB and that the
    fail-closed THROW code remains in the script. Failure-path THROW text is
    covered by the static unit tests above.
    """
    text = PREFLIGHT.read_text(encoding="utf-8")
    assert "THROW 51009" in text

    client = sql_server_client_or_skip(resolved_sqlserver_connection_string_for_tests())
    ensure_sql_migrations_applied(client)

    with client.cursor() as cur:
        cur.execute(text)
        # Drain diagnostic result sets (status counts, then @errors).
        while True:
            try:
                rows = cur.fetchall()
            except Exception:
                rows = []
            if not cur.nextset():
                break
            _ = rows
        # Belt-and-suspenders for ODBC pool reuse after SET NOCOUNT ON.
        cur.execute("SET NOCOUNT OFF")

    # Sanity: lease columns from 0110 are present on a healthy DB.
    with client.cursor() as cur:
        cur.execute(
            """
            SELECT
              COL_LENGTH(N'dbo.local_csv_imports', N'materialization_owner'),
              COL_LENGTH(N'dbo.local_csv_imports', N'materialization_lease_expires_at'),
              COL_LENGTH(N'dbo.local_csv_imports', N'fencing_version')
            """
        )
        row = cur.fetchone()
    assert row is not None
    assert row[0] is not None
    assert row[1] is not None
    assert row[2] is not None
