"""SQL Stage 2 — tenant list/get isolation for clients and inventories.

Skipped when SQL Server is unavailable.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from src.application.errors import ClientNotFoundError, InventoryNotFoundError
from src.application.use_cases.clients.get_client import GetClientUseCase
from src.application.use_cases.clients.list_clients import ListClientsUseCase
from src.application.use_cases.inventories.get_inventory import GetInventoryUseCase
from src.domain.client.entities import Client, ClientStatus
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.infrastructure.repositories.sql_client_repository import SqlClientRepository
from src.infrastructure.repositories.sql_inventory_repository import SqlInventoryRepository
from tests.support.access_principal_helpers import company_principal, platform_principal
from tests.support.sql_integration import sql_server_client_or_skip
from tests.support.sqlserver_test_connection import resolved_sqlserver_connection_string_for_tests

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def sql_client():
    return sql_server_client_or_skip(resolved_sqlserver_connection_string_for_tests())


def _now() -> datetime:
    return datetime.now(timezone.utc)


def test_sql_tenant_clients_and_inventories_scoped(sql_client) -> None:
    suffix = uuid.uuid4().hex[:10]
    client_a = f"cli-a-{suffix}"
    client_b = f"cli-b-{suffix}"
    inv_a = f"inv-a-{suffix}"
    inv_b = f"inv-b-{suffix}"
    now = _now()

    clients = SqlClientRepository(sql_client)
    inventories = SqlInventoryRepository(sql_client)
    clients.save(
        Client(
            id=client_a,
            name=f"A-{suffix}",
            status=ClientStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
    )
    clients.save(
        Client(
            id=client_b,
            name=f"B-{suffix}",
            status=ClientStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
    )
    inventories.save(
        Inventory(
            id=inv_a,
            name=f"IA-{suffix}",
            status=InventoryStatus.DRAFT,
            created_at=now,
            updated_at=now,
            client_id=client_a,
        )
    )
    inventories.save(
        Inventory(
            id=inv_b,
            name=f"IB-{suffix}",
            status=InventoryStatus.DRAFT,
            created_at=now,
            updated_at=now,
            client_id=client_b,
        )
    )

    listed_a = ListClientsUseCase(clients).execute(company_principal(client_a))
    assert [c.id for c in listed_a] == [client_a]

    assert GetClientUseCase(clients).execute(client_a, company_principal(client_a)).id == client_a
    with pytest.raises(ClientNotFoundError):
        GetClientUseCase(clients).execute(client_b, company_principal(client_a))

    scoped = inventories.list_for_client(client_a)
    assert {i.id for i in scoped} == {inv_a}

    assert GetInventoryUseCase(inventories).execute(
        inv_a, company_principal(client_a)
    ).id == inv_a
    with pytest.raises(InventoryNotFoundError):
        GetInventoryUseCase(inventories).execute(inv_b, company_principal(client_a))

    plat_clients = ListClientsUseCase(clients).execute(platform_principal())
    assert {client_a, client_b}.issubset({c.id for c in plat_clients})
