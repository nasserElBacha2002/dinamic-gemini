"""
Integration tests for SqlInventoryRepository — Épica 2.

Run against a real SQL Server when SQLSERVER_CONNECTION_STRING (or equivalent env) is set.
Skips when DB is not configured. Requires v3 schema (inventories table) to be applied.
"""

from __future__ import annotations

import pytest

from src.database.sqlserver import now_utc
from src.domain.client.entities import Client, ClientStatus
from src.domain.inventory.entities import Inventory, InventoryProcessingMode, InventoryStatus
from src.infrastructure.repositories.sql_client_repository import SqlClientRepository
from src.infrastructure.repositories.sql_inventory_repository import SqlInventoryRepository
from tests.support.sql_integration import sql_server_client_or_skip
from tests.support.sqlserver_test_connection import resolved_sqlserver_connection_string_for_tests

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def sql_client():
    return sql_server_client_or_skip(resolved_sqlserver_connection_string_for_tests())


@pytest.fixture
def repo(sql_client):
    return SqlInventoryRepository(sql_client)


@pytest.fixture
def client_repo(sql_client):
    return SqlClientRepository(sql_client)


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


def test_sql_inventory_repository_get_by_id_missing_returns_none(
    repo: SqlInventoryRepository,
) -> None:
    assert repo.get_by_id("nonexistent-id-xyz") is None


def test_sql_inventory_repository_round_trips_processing_mode_and_primary_snapshot(
    repo: SqlInventoryRepository,
) -> None:
    now = now_utc()
    inv = Inventory(
        id="test-epica2-mode-snap",
        name="Mode Snapshot",
        status=InventoryStatus.DRAFT,
        created_at=now,
        updated_at=now,
        processing_mode=InventoryProcessingMode.TEST,
        primary_provider_name="prov-x",
        primary_model_name="model-y",
        primary_prompt_key="prompt-z",
        primary_prompt_version="pv1",
    )
    repo.save(inv)
    loaded = repo.get_by_id("test-epica2-mode-snap")
    assert loaded is not None
    assert loaded.processing_mode == InventoryProcessingMode.TEST
    assert loaded.primary_provider_name == "prov-x"
    assert loaded.primary_model_name == "model-y"
    assert loaded.primary_prompt_key == "prompt-z"
    assert loaded.primary_prompt_version == "pv1"
    assert loaded.client_id is None


def test_sql_inventory_repository_round_trips_nullable_client_id_none(
    repo: SqlInventoryRepository,
) -> None:
    now = now_utc()
    inv = Inventory(
        id="test-epica2-client-null",
        name="Client Null",
        status=InventoryStatus.DRAFT,
        created_at=now,
        updated_at=now,
        client_id=None,
    )
    repo.save(inv)
    loaded = repo.get_by_id("test-epica2-client-null")
    assert loaded is not None
    assert loaded.client_id is None


def test_sql_inventory_repository_round_trips_non_null_client_id(
    repo: SqlInventoryRepository,
    client_repo: SqlClientRepository,
) -> None:
    now = now_utc()
    client_repo.save(
        Client(
            id="test-client-a3-1",
            name="A3 Parent",
            status=ClientStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
    )
    inv = Inventory(
        id="test-epica2-client-set",
        name="Client Set",
        status=InventoryStatus.DRAFT,
        created_at=now,
        updated_at=now,
        client_id="test-client-a3-1",
    )
    repo.save(inv)
    loaded = repo.get_by_id("test-epica2-client-set")
    assert loaded is not None
    assert loaded.client_id == "test-client-a3-1"
