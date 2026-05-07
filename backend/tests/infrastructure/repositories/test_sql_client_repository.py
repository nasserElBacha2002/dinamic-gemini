"""Integration tests for SqlClientRepository — Phase A1."""

from __future__ import annotations

import pytest

from src.database.sqlserver import now_utc
from src.domain.client.entities import Client, ClientStatus
from src.infrastructure.repositories.sql_client_repository import SqlClientRepository
from tests.support.sql_integration import sql_server_client_or_skip
from tests.support.sqlserver_test_connection import resolved_sqlserver_connection_string_for_tests

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def sql_client():
    return sql_server_client_or_skip(resolved_sqlserver_connection_string_for_tests())


@pytest.fixture
def repo(sql_client):
    return SqlClientRepository(sql_client)


def test_sql_client_repository_save_and_get_by_id(repo: SqlClientRepository) -> None:
    now = now_utc()
    client = Client(
        id="test-client-a1-001",
        name="SQL Client A",
        status=ClientStatus.ACTIVE,
        created_at=now,
        updated_at=now,
    )
    repo.save(client)
    loaded = repo.get_by_id("test-client-a1-001")
    assert loaded is not None
    assert loaded.id == client.id
    assert loaded.name == client.name
    assert loaded.status == ClientStatus.ACTIVE


def test_sql_client_repository_list_all_includes_saved(repo: SqlClientRepository) -> None:
    now = now_utc()
    client = Client(
        id="test-client-a1-002",
        name="SQL Client B",
        status=ClientStatus.INACTIVE,
        created_at=now,
        updated_at=now,
    )
    repo.save(client)
    rows = repo.list_all()
    assert "test-client-a1-002" in [r.id for r in rows]

