"""
Integration tests for SqlAisleRepository — Épica 3.

Run when SQL Server is configured (same as test_sql_inventory_repository).
Requires v3 schema (inventories and aisles tables). Creates a temporary inventory for FK.
"""

from __future__ import annotations

import os

import pytest

from src.database.sqlserver import now_utc
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.infrastructure.repositories.sql_aisle_repository import SqlAisleRepository
from src.infrastructure.repositories.sql_inventory_repository import SqlInventoryRepository
from tests.support.sql_integration import sql_server_client_or_skip

pytestmark = pytest.mark.integration


def _connection_string() -> str:
    raw = (os.getenv("SQLSERVER_CONNECTION_STRING") or "").strip()
    if raw:
        return raw
    server = (os.getenv("SQLSERVER_SERVER") or "").strip()
    database = (os.getenv("SQLSERVER_DATABASE") or "").strip()
    uid = (os.getenv("SQLSERVER_UID") or "").strip()
    pwd = (os.getenv("SQLSERVER_PWD") or "").strip()
    if server and database and uid and pwd:
        driver = (os.getenv("SQLSERVER_DRIVER") or "").strip()
        if not driver:
            try:
                import pyodbc

                for d in pyodbc.drivers():
                    if "SQL Server" in d:
                        driver = d
                        break
            except Exception:
                pass
        if driver:
            return f"DRIVER={{{driver}}};SERVER={server};DATABASE={database};UID={uid};PWD={pwd};TrustServerCertificate=yes"
    return ""


@pytest.fixture(scope="module")
def sql_client():
    return sql_server_client_or_skip(_connection_string())


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
