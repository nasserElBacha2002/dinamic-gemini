"""Targeted SQL Server cleanup for worker Phase 1 integration tests."""

from __future__ import annotations

from src.database.sqlserver import SqlServerClient
from src.env_settings.sqlserver_pytest_policy import assert_pytest_sqlserver_database_is_safe


def assert_sql_integration_database_is_safe() -> None:
    """Raise when configured database is not explicitly marked as a test database."""
    assert_pytest_sqlserver_database_is_safe()


def cleanup_worker_phase1_sql_scope(
    client: SqlServerClient,
    *,
    inventory_id: str,
    aisle_id: str,
    job_id: str,
) -> None:
    """Delete rows created by a worker Phase 1 SQL test in FK-safe order."""
    with client.cursor() as cur:
        cur.execute(
            "DELETE FROM evidences WHERE entity_id IN (SELECT id FROM positions WHERE aisle_id = ? AND job_id = ?)",
            (aisle_id, job_id),
        )
        cur.execute(
            "DELETE FROM product_records WHERE position_id IN (SELECT id FROM positions WHERE aisle_id = ? AND job_id = ?)",
            (aisle_id, job_id),
        )
        cur.execute(
            "DELETE FROM positions WHERE aisle_id = ? AND job_id = ?",
            (aisle_id, job_id),
        )
        cur.execute(
            "DELETE FROM raw_labels WHERE inventory_id = ? AND aisle_id = ? AND job_id = ?",
            (inventory_id, aisle_id, job_id),
        )
        cur.execute(
            "DELETE FROM normalized_labels WHERE inventory_id = ? AND aisle_id = ? AND job_id = ?",
            (inventory_id, aisle_id, job_id),
        )
        cur.execute(
            "DELETE FROM final_count_records WHERE inventory_id = ? AND aisle_id = ? AND job_id = ?",
            (inventory_id, aisle_id, job_id),
        )
        cur.execute("DELETE FROM inventory_jobs WHERE id = ?", (job_id,))
        cur.execute("DELETE FROM aisles WHERE id = ?", (aisle_id,))
        cur.execute("DELETE FROM inventories WHERE id = ?", (inventory_id,))
