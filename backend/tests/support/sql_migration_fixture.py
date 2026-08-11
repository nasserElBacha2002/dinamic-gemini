"""Apply pending SQL migrations for integration tests (fail with actionable context)."""

from __future__ import annotations

import pytest

from src.config import load_settings
from src.database.migrations import MigrationStatus, get_migration_status, run_pending_migrations
from src.database.sqlserver import SqlServerClient


def _database_name(client: SqlServerClient) -> str:
    with client.cursor() as cur:
        cur.execute("SELECT DB_NAME()")
        row = cur.fetchone()
    return str(getattr(row, "DB_NAME()", row[0] if row else "?"))


def ensure_sql_migrations_applied(client: SqlServerClient) -> MigrationStatus:
    """Run pending migrations for the configured schema service; fail if they cannot apply."""
    settings = load_settings()
    service = settings.db_schema_service_name
    before = get_migration_status(client=client, service=service)
    if not before.pending_versions:
        return before
    try:
        return run_pending_migrations(
            client=client,
            service=service,
            deployment_id=settings.deployment_id,
            lock_timeout_sec=settings.db_schema_migration_lock_timeout_sec,
        )
    except Exception as exc:
        pytest.fail(
            "Failed to apply pending SQL migrations. "
            f"database={_database_name(client)!r} service={service!r} "
            f"current_version={before.current_version!r} "
            f"pending_count={len(before.pending_versions)} "
            f"next_pending={before.pending_versions[0]!r}. "
            "Ensure the test database was bootstrapped with schema.sql before incremental "
            f"migrations, or point integration tests at a fully migrated database. Error: {exc}"
        )
