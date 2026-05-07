"""Integration tests for SqlClientSupplierRepository — Phase A2."""

from __future__ import annotations

import pytest

from src.database.sqlserver import now_utc
from src.domain.client.entities import Client, ClientStatus
from src.domain.client_supplier.entities import ClientSupplier, ClientSupplierStatus
from src.infrastructure.repositories.sql_client_repository import SqlClientRepository
from src.infrastructure.repositories.sql_client_supplier_repository import (
    SqlClientSupplierRepository,
)
from tests.support.sql_integration import sql_server_client_or_skip
from tests.support.sqlserver_test_connection import resolved_sqlserver_connection_string_for_tests

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def sql_client():
    return sql_server_client_or_skip(resolved_sqlserver_connection_string_for_tests())


@pytest.fixture
def repos(sql_client):
    return SqlClientRepository(sql_client), SqlClientSupplierRepository(sql_client)


def _ensure_client(client_repo: SqlClientRepository, client_id: str) -> None:
    now = now_utc()
    client_repo.save(
        Client(
            id=client_id,
            name=f"Client {client_id}",
            status=ClientStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
    )


def test_sql_client_supplier_repository_save_get_list(repos) -> None:
    client_repo, supplier_repo = repos
    _ensure_client(client_repo, "test-client-a2-1")
    now = now_utc()
    supplier = ClientSupplier(
        id="test-supplier-a2-1",
        client_id="test-client-a2-1",
        name="Acme A2",
        status=ClientSupplierStatus.ACTIVE,
        created_at=now,
        updated_at=now,
    )
    supplier_repo.save(supplier)
    loaded = supplier_repo.get_by_id("test-supplier-a2-1")
    assert loaded is not None
    assert loaded.client_id == "test-client-a2-1"
    assert loaded.name == "Acme A2"
    listed = supplier_repo.list_by_client("test-client-a2-1")
    assert "test-supplier-a2-1" in [r.id for r in listed]

