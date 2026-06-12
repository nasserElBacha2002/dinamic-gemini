"""Post-cleanup verification for optional SQL integration tests."""

from __future__ import annotations

from src.application.ports.repositories import (
    AisleRepository,
    InventoryRepository,
    PositionRepository,
)
from src.database.sqlserver import SqlServerClient


def verify_sql_scope_fully_removed(
    client: SqlServerClient,
    *,
    inventory_repo: InventoryRepository,
    aisle_repo: AisleRepository,
    position_repo: PositionRepository,
    inventory_id: str,
    aisle_id: str,
    job_id: str,
) -> None:
    """Assert every SQL row created for a test scope is gone after cleanup."""
    assert list(position_repo.list_by_aisle(aisle_id, job_id=job_id)) == []
    with client.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM product_records WHERE position_id IN "
            "(SELECT id FROM positions WHERE aisle_id = ? AND job_id = ?)",
            (aisle_id, job_id),
        )
        product_count = int(cur.fetchone()[0])
        cur.execute(
            "SELECT COUNT(*) FROM evidences WHERE entity_id IN "
            "(SELECT id FROM positions WHERE aisle_id = ? AND job_id = ?)",
            (aisle_id, job_id),
        )
        evidence_count = int(cur.fetchone()[0])
        cur.execute("SELECT COUNT(*) FROM positions WHERE aisle_id = ? AND job_id = ?", (aisle_id, job_id))
        position_count = int(cur.fetchone()[0])
    assert position_count == 0
    assert product_count == 0
    assert evidence_count == 0
    assert inventory_repo.get_by_id(inventory_id) is None
    assert aisle_repo.get_by_id(aisle_id) is None
