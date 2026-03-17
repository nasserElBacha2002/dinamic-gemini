"""
Integration tests for SqlInventoryVisualReferenceRepository — v3.2.4.

Run against a real SQL Server when SQLSERVER_CONNECTION_STRING (or equivalent) is set.
Skips when DB is not configured. Requires inventory_visual_references table to exist.
"""

from __future__ import annotations

import os
import pytest

from src.database.sqlserver import SqlServerClient, now_utc
from src.domain.inventory.visual_reference import InventoryVisualReference
from src.infrastructure.repositories.sql_inventory_repository import SqlInventoryRepository
from src.infrastructure.repositories.sql_inventory_visual_reference_repository import (
    SqlInventoryVisualReferenceRepository,
)


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
    cs = _connection_string()
    if not cs:
        pytest.skip("SQL Server not configured (set SQLSERVER_CONNECTION_STRING or server/database/uid/pwd)")
    return SqlServerClient(cs)


@pytest.fixture
def inventory_repo(sql_client):
    return SqlInventoryRepository(sql_client)


@pytest.fixture
def ref_repo(sql_client):
    return SqlInventoryVisualReferenceRepository(sql_client)


@pytest.fixture
def ensure_inventory(inventory_repo):
    """Ensure an inventory exists for FK; use a dedicated test id to avoid clashes."""
    from src.domain.inventory.entities import Inventory, InventoryStatus
    now = now_utc()
    inv = Inventory(
        id="test-v324-inv-ref",
        name="Test inventory for visual refs",
        status=InventoryStatus.DRAFT,
        created_at=now,
        updated_at=now,
    )
    inventory_repo.save(inv)
    yield inv.id


def test_sql_save_and_list_by_inventory(ref_repo, ensure_inventory) -> None:
    inventory_id = ensure_inventory
    now = now_utc()
    ref = InventoryVisualReference(
        id="test-v324-ref-001",
        inventory_id=inventory_id,
        filename="example.png",
        storage_path=f"inventories/{inventory_id}/visual_references/test-v324-ref-001.png",
        mime_type="image/png",
        file_size=2048,
        created_at=now,
    )
    ref_repo.create(ref)
    listed = ref_repo.list_by_inventory(inventory_id)
    assert len(listed) >= 1
    found = [r for r in listed if r.id == ref.id]
    assert len(found) == 1
    assert found[0].filename == "example.png"
    assert found[0].file_size == 2048


def test_sql_list_by_inventory_empty_for_other_inventory(ref_repo, ensure_inventory) -> None:
    """List for a different inventory returns no refs (isolation)."""
    other_inventory_id = "nonexistent-inv-id-for-list"
    listed = ref_repo.list_by_inventory(other_inventory_id)
    assert len(listed) == 0


def test_sql_multiple_references_same_inventory(ref_repo, ensure_inventory) -> None:
    inventory_id = ensure_inventory
    now = now_utc()
    for i in range(2):
        ref = InventoryVisualReference(
            id=f"test-v324-multi-{i}",
            inventory_id=inventory_id,
            filename=f"img{i}.jpg",
            storage_path=f"inventories/{inventory_id}/visual_references/test-v324-multi-{i}.jpg",
            mime_type="image/jpeg",
            file_size=100 * (i + 1),
            created_at=now,
        )
        ref_repo.create(ref)
    listed = ref_repo.list_by_inventory(inventory_id)
    ids = [r.id for r in listed if r.id.startswith("test-v324-multi-")]
    assert len(ids) == 2
    assert "test-v324-multi-0" in ids and "test-v324-multi-1" in ids
