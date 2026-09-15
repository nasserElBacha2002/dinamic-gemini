"""Stage 2 — tenant isolation matrix for clients / inventories / bulk (unit)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.application.errors import (
    ClientNotFoundError,
    InventoryNotFoundError,
    PlatformOnlyOperationError,
)
from src.application.services.operational_execution_config_resolver import (
    OperationalPrimaryExecutionConfig,
)
from src.application.use_cases.clients.create_client import CreateClientCommand, CreateClientUseCase
from src.application.use_cases.clients.get_client import GetClientUseCase
from src.application.use_cases.clients.list_clients import ListClientsUseCase
from src.application.use_cases.clients.update_client import UpdateClientCommand, UpdateClientUseCase
from src.application.use_cases.inventories.create_inventory import (
    CreateInventoryCommand,
    CreateInventoryUseCase,
)
from src.application.use_cases.inventories.get_inventory import GetInventoryUseCase
from src.application.use_cases.inventories.list_inventory_list_items import (
    ListInventoryListItemsUseCase,
)
from src.application.use_cases.inventories.soft_delete_inventories import (
    SoftDeleteInventoriesCommand,
    SoftDeleteInventoriesUseCase,
)
from src.domain.client.entities import Client, ClientStatus
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.infrastructure.repositories.memory_aisle_repository import MemoryAisleRepository
from src.infrastructure.repositories.memory_client_repository import MemoryClientRepository
from src.infrastructure.repositories.memory_inventory_repository import MemoryInventoryRepository
from src.infrastructure.repositories.memory_position_repository import MemoryPositionRepository
from tests.support.access_principal_helpers import company_principal, platform_principal
from tests.support.processing_test_constants import STUB_PRIMARY_MODEL, STUB_PRIMARY_PROVIDER


class _FixedClock:
    def __init__(self) -> None:
        self._now = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)

    def now(self) -> datetime:
        return self._now


class _StubOperational:
    def resolve(self, settings):
        _ = settings
        return OperationalPrimaryExecutionConfig(
            provider_name=STUB_PRIMARY_PROVIDER,
            model_name=STUB_PRIMARY_MODEL,
            prompt_key="global_v21",
            prompt_version=None,
        )


@pytest.fixture
def clients_ab() -> MemoryClientRepository:
    repo = MemoryClientRepository()
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for cid, name in (("client-a", "A"), ("client-b", "B")):
        repo.save(
            Client(
                id=cid,
                name=name,
                status=ClientStatus.ACTIVE,
                created_at=now,
                updated_at=now,
            )
        )
    return repo


@pytest.fixture
def inventories_ab(clients_ab: MemoryClientRepository) -> MemoryInventoryRepository:
    _ = clients_ab
    repo = MemoryInventoryRepository()
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for iid, cid in (("inv-a", "client-a"), ("inv-b", "client-b")):
        repo.save(
            Inventory(
                id=iid,
                name=iid,
                status=InventoryStatus.DRAFT,
                created_at=now,
                updated_at=now,
                client_id=cid,
            )
        )
    return repo


def test_company_a_gets_own_client_not_b(clients_ab: MemoryClientRepository) -> None:
    uc = GetClientUseCase(clients_ab)
    assert uc.execute("client-a", company_principal("client-a")).id == "client-a"
    with pytest.raises(ClientNotFoundError):
        uc.execute("client-b", company_principal("client-a"))


def test_company_b_cannot_get_a(clients_ab: MemoryClientRepository) -> None:
    with pytest.raises(ClientNotFoundError):
        GetClientUseCase(clients_ab).execute("client-a", company_principal("client-b"))


def test_company_a_lists_only_a(clients_ab: MemoryClientRepository) -> None:
    rows = ListClientsUseCase(clients_ab).execute(company_principal("client-a"))
    assert [c.id for c in rows] == ["client-a"]


def test_platform_lists_a_and_b(clients_ab: MemoryClientRepository) -> None:
    rows = ListClientsUseCase(clients_ab).execute(platform_principal())
    assert {c.id for c in rows} == {"client-a", "client-b"}


def test_company_cannot_create_client(clients_ab: MemoryClientRepository) -> None:
    uc = CreateClientUseCase(clients_ab, _FixedClock())
    with pytest.raises(PlatformOnlyOperationError):
        uc.execute(
            CreateClientCommand(name="X", principal=company_principal("client-a"))
        )


def test_platform_can_create_client(clients_ab: MemoryClientRepository) -> None:
    uc = CreateClientUseCase(clients_ab, _FixedClock())
    created = uc.execute(
        CreateClientCommand(name="New Co", principal=platform_principal())
    )
    assert created.name == "New Co"


def test_company_cannot_update_other_client(clients_ab: MemoryClientRepository) -> None:
    uc = UpdateClientUseCase(clients_ab, _FixedClock())
    with pytest.raises(ClientNotFoundError):
        uc.execute(
            UpdateClientCommand(
                client_id="client-b",
                principal=company_principal("client-a"),
                name="Hacked",
            )
        )
    assert clients_ab.get_by_id("client-b").name == "B"  # type: ignore[union-attr]


def test_company_a_inventory_scope(inventories_ab: MemoryInventoryRepository) -> None:
    uc = GetInventoryUseCase(inventories_ab)
    assert uc.execute("inv-a", company_principal("client-a")).id == "inv-a"
    with pytest.raises(InventoryNotFoundError):
        uc.execute("inv-b", company_principal("client-a"))


def test_company_a_lists_only_own_inventories(
    inventories_ab: MemoryInventoryRepository, clients_ab: MemoryClientRepository
) -> None:
    uc = ListInventoryListItemsUseCase(
        inventories_ab,
        MemoryAisleRepository(),
        MemoryPositionRepository(),
        clients_ab,
    )
    rows, total = uc.execute(principal=company_principal("client-a"))
    assert total == 1
    assert rows[0].inventory.id == "inv-a"


def test_company_cannot_create_inventory_for_other_client(
    inventories_ab: MemoryInventoryRepository, clients_ab: MemoryClientRepository
) -> None:
    uc = CreateInventoryUseCase(
        inventories_ab,
        clients_ab,
        _FixedClock(),
        _StubOperational(),
        lambda: object(),
    )
    with pytest.raises(ClientNotFoundError):
        uc.execute(
            CreateInventoryCommand(
                name="X",
                client_id="client-b",
                principal=company_principal("client-a"),
            )
        )


def test_bulk_mixed_tenant_modifies_nothing(
    inventories_ab: MemoryInventoryRepository,
) -> None:
    uc = SoftDeleteInventoriesUseCase(inventories_ab, _FixedClock())
    result = uc.execute(
        SoftDeleteInventoriesCommand(
            inventory_ids=("inv-a", "inv-b"),
            principal=company_principal("client-a"),
        )
    )
    assert result.deleted_ids == ()
    assert "inv-b" in result.not_found_ids
    assert inventories_ab.get_by_id("inv-a").deleted_at is None  # type: ignore[union-attr]
    assert inventories_ab.get_by_id("inv-b").deleted_at is None  # type: ignore[union-attr]


def test_company_without_client_id_fail_closed(
    inventories_ab: MemoryInventoryRepository,
) -> None:
    from src.application.dto.access_principal import AccessPrincipal

    principal = AccessPrincipal(
        actor_id="u",
        client_id=None,
        roles=frozenset({"company_admin"}),
        is_platform=False,
    )
    with pytest.raises(InventoryNotFoundError):
        GetInventoryUseCase(inventories_ab).execute("inv-a", principal)
