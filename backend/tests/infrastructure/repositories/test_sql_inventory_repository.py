"""
Integration tests for SqlInventoryRepository — Épica 2.

Run against a real SQL Server when SQLSERVER_CONNECTION_STRING (or equivalent env) is set.
Skips when DB is not configured. Requires v3 schema (inventories table) to be applied.
"""

from __future__ import annotations

import os
import pytest

from src.database.sqlserver import SqlServerClient, now_utc
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.infrastructure.repositories.sql_inventory_repository import SqlInventoryRepository


def _connection_string() -> str:
    raw = (os.getenv("SQLSERVER_CONNECTION_STRING") or "").strip()
    if raw:
        return raw
    # Build from components like config does
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
    cs = _connection_string()
    if not cs:
        pytest.skip("SQL Server not configured (set SQLSERVER_CONNECTION_STRING or server/database/uid/pwd)")
    return SqlServerClient(cs)


@pytest.fixture
def repo(sql_client):
    return SqlInventoryRepository(sql_client)


def test_sql_inventory_repository_save_and_get_by_id(repo: SqlInventoryRepository) -> None:
    now = now_utc()
    inv = Inventory(
        id="test-epica2-001",
        name="SQL Test Inventory",
        status=InventoryStatus.DRAFT,
        created_at=now,
        updated_at=now,
    )
    repo.save(inv)
    loaded = repo.get_by_id("test-epica2-001")
    assert loaded is not None
    assert loaded.id == inv.id
    assert loaded.name == inv.name
    assert loaded.status == InventoryStatus.DRAFT


def test_sql_inventory_repository_list_all_includes_saved(repo: SqlInventoryRepository) -> None:
    now = now_utc()
    inv = Inventory(
        id="test-epica2-002",
        name="List Test",
        status=InventoryStatus.DRAFT,
        created_at=now,
        updated_at=now,
    )
    repo.save(inv)
    all_inv = repo.list_all()
    ids = [i.id for i in all_inv]
    assert "test-epica2-002" in ids


def test_sql_inventory_repository_get_by_id_missing_returns_none(repo: SqlInventoryRepository) -> None:
    assert repo.get_by_id("nonexistent-id-xyz") is None
