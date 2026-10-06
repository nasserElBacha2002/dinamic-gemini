"""Raspberry inventory list is scoped to the requested client."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.application.errors import ClientNotFoundError
from src.application.use_cases.inventories.list_raspberry_inventories import (
    ListRaspberryInventoriesCommand,
    ListRaspberryInventoriesUseCase,
)
from src.domain.client.entities import Client, ClientStatus
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.infrastructure.repositories.memory_client_repository import MemoryClientRepository
from src.infrastructure.repositories.memory_inventory_repository import MemoryInventoryRepository


def _now() -> datetime:
    return datetime.now(timezone.utc)


def test_list_raspberry_inventories_returns_only_requested_client() -> None:
    clients = MemoryClientRepository()
    inventories = MemoryInventoryRepository()
    now = _now()
    clients.save(
        Client(
            id="client-a",
            name="A",
            status=ClientStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
    )
    clients.save(
        Client(
            id="client-b",
            name="B",
            status=ClientStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
    )
    inventories.save(
        Inventory(
            id="inv-a",
            name="A",
            status=InventoryStatus.DRAFT,
            created_at=now,
            updated_at=now,
            client_id="client-a",
        )
    )
    inventories.save(
        Inventory(
            id="inv-b",
            name="B",
            status=InventoryStatus.DRAFT,
            created_at=now,
            updated_at=now,
            client_id="client-b",
        )
    )
    use_case = ListRaspberryInventoriesUseCase(
        client_repo=clients,
        inventory_repo=inventories,
    )
    result = use_case.execute(ListRaspberryInventoriesCommand(client_id="client-a"))
    assert [row.id for row in result] == ["inv-a"]
    assert all(row.client_id == "client-a" for row in result)


def test_list_raspberry_inventories_unknown_client_is_not_found() -> None:
    use_case = ListRaspberryInventoriesUseCase(
        client_repo=MemoryClientRepository(),
        inventory_repo=MemoryInventoryRepository(),
    )
    with pytest.raises(ClientNotFoundError):
        use_case.execute(ListRaspberryInventoriesCommand(client_id="missing"))
