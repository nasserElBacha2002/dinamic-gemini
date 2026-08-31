"""
Integration tests for SqlAisleRepository — Épica 3.

Run when SQL Server is configured (same as test_sql_inventory_repository).
Requires v3 schema (inventories and aisles tables). Creates a temporary inventory for FK.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.database.sqlserver import now_utc
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.infrastructure.repositories.sql_aisle_repository import SqlAisleRepository
from src.infrastructure.repositories.sql_inventory_repository import SqlInventoryRepository
from tests.support.sql_integration import sql_server_client_or_skip
from tests.support.sqlserver_test_connection import resolved_sqlserver_connection_string_for_tests

pytestmark = pytest.mark.integration

_MIGRATION_0100 = (
    Path(__file__).resolve().parents[3]
    / "src"
    / "database"
    / "migrations"
    / "versions"
    / "0100_label_recognition_profiles_phase1.sql"
)


def _apply_migration_0100_if_needed(sql_client) -> None:
    with sql_client.cursor() as cur:
        cur.execute(
            """
            SELECT COL_LENGTH('aisles', 'item_profile_source_override') AS col_len
            """
        )
        row = cur.fetchone()
        if row and row.col_len is not None:
            return
    sql = _MIGRATION_0100.read_text(encoding="utf-8")
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
    with sql_client.cursor() as cur:
        for batch in batches:
            if batch.strip():
                cur.execute(batch)


@pytest.fixture(scope="module")
def sql_client():
    client = sql_server_client_or_skip(resolved_sqlserver_connection_string_for_tests())
    _apply_migration_0100_if_needed(client)
    return client


@pytest.fixture
def inventory_repo(sql_client):
    return SqlInventoryRepository(sql_client)


@pytest.fixture
def aisle_repo(sql_client, inventory_repo):
    """Ensure at least one inventory exists for aisle FK."""
    now = now_utc()
    inv = Inventory(
        id="test-epica3-inv-001",
        name="SQL Aisle Test Inventory",
        status=InventoryStatus.DRAFT,
        created_at=now,
        updated_at=now,
    )
    inventory_repo.save(inv)
    with sql_client.cursor() as cur:
        cur.execute(
            """
            IF NOT EXISTS (SELECT 1 FROM clients WHERE id = ?)
                INSERT INTO clients (id, name, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
            """,
            (
                "test-epica3-client-001",
                "test-epica3-client-001",
                "SQL Aisle Test Client",
                "active",
                now,
                now,
            ),
        )
        cur.execute(
            """
            IF NOT EXISTS (SELECT 1 FROM client_suppliers WHERE id = ?)
                INSERT INTO client_suppliers (id, client_id, name, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "test-epica3-client-supplier-001",
                "test-epica3-client-supplier-001",
                "test-epica3-client-001",
                "SQL Aisle Test Supplier",
                "active",
                now,
                now,
            ),
        )
    return SqlAisleRepository(sql_client)


def test_sql_aisle_repository_save_and_get_by_id(aisle_repo: SqlAisleRepository) -> None:
    now = now_utc()
    aisle = Aisle(
        id="test-epica3-aisle-001",
        inventory_id="test-epica3-inv-001",
        code="A-01",
        status=AisleStatus.CREATED,
        created_at=now,
        updated_at=now,
    )
    aisle_repo.save(aisle)
    loaded = aisle_repo.get_by_id("test-epica3-aisle-001")
    assert loaded is not None
    assert loaded.id == aisle.id
    assert loaded.code == "A-01"
    assert loaded.inventory_id == "test-epica3-inv-001"
    assert loaded.status == AisleStatus.CREATED
    assert loaded.client_supplier_id is None


def test_sql_aisle_repository_list_by_inventory_includes_saved(
    aisle_repo: SqlAisleRepository,
) -> None:
    now = now_utc()
    aisle = Aisle(
        id="test-epica3-aisle-002",
        inventory_id="test-epica3-inv-001",
        code="A-02",
        status=AisleStatus.CREATED,
        created_at=now,
        updated_at=now,
    )
    aisle_repo.save(aisle)
    listed = aisle_repo.list_by_inventory("test-epica3-inv-001")
    codes = [a.code for a in listed]
    assert "A-02" in codes


def test_sql_aisle_repository_get_by_inventory_and_code(aisle_repo: SqlAisleRepository) -> None:
    now = now_utc()
    aisle = Aisle(
        id="test-epica3-aisle-003",
        inventory_id="test-epica3-inv-001",
        code="A-03",
        status=AisleStatus.CREATED,
        created_at=now,
        updated_at=now,
    )
    aisle_repo.save(aisle)
    found = aisle_repo.get_by_inventory_and_code("test-epica3-inv-001", "A-03")
    assert found is not None
    assert found.id == "test-epica3-aisle-003"
    assert aisle_repo.get_by_inventory_and_code("test-epica3-inv-001", "nonexistent") is None


def test_sql_aisle_repository_get_by_id_missing_returns_none(
    aisle_repo: SqlAisleRepository,
) -> None:
    assert aisle_repo.get_by_id("nonexistent-aisle-id") is None


def test_sql_aisle_repository_profile_overrides_round_trip(
    aisle_repo: SqlAisleRepository,
) -> None:
    from src.domain.label_profiles.kinds import LabelProfileSource

    now = now_utc()
    aisle_id = "test-epica3-aisle-overrides"
    aisle = Aisle(
        id=aisle_id,
        inventory_id="test-epica3-inv-001",
        code="A-OVR",
        status=AisleStatus.CREATED,
        created_at=now,
        updated_at=now,
        item_profile_source_override=LabelProfileSource.DINAMIC,
        position_profile_source_override=LabelProfileSource.SUPPLIER,
    )
    aisle_repo.save(aisle)
    loaded = aisle_repo.get_by_id(aisle_id)
    assert loaded is not None
    assert loaded.item_profile_source_override is LabelProfileSource.DINAMIC
    assert loaded.position_profile_source_override is LabelProfileSource.SUPPLIER

    loaded.item_profile_source_override = None
    loaded.position_profile_source_override = None
    aisle_repo.save(loaded)
    cleared = aisle_repo.get_by_id(aisle_id)
    assert cleared is not None
    assert cleared.item_profile_source_override is None
    assert cleared.position_profile_source_override is None

    listed = aisle_repo.list_by_inventory("test-epica3-inv-001")
    assert any(a.id == aisle_id for a in listed)


def test_sql_aisle_repository_round_trip_with_client_supplier_id(
    aisle_repo: SqlAisleRepository,
) -> None:
    now = now_utc()
    aisle = Aisle(
        id="test-epica3-aisle-004",
        inventory_id="test-epica3-inv-001",
        code="A-04",
        status=AisleStatus.CREATED,
        created_at=now,
        updated_at=now,
        client_supplier_id="test-epica3-client-supplier-001",
    )
    aisle_repo.save(aisle)
    loaded = aisle_repo.get_by_id("test-epica3-aisle-004")
    assert loaded is not None
    assert loaded.client_supplier_id == "test-epica3-client-supplier-001"
