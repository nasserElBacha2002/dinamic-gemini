"""Tests for CreateInventoryUseCase."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from src.application.errors import ClientNotFoundError
from src.application.ports.repositories import ClientRepository, InventoryRepository
from src.application.services.operational_execution_config_resolver import (
    OperationalPrimaryExecutionConfig,
)
from src.application.use_cases.inventories.create_inventory import (
    CreateInventoryCommand,
    CreateInventoryUseCase,
)
from src.domain.client.entities import Client, ClientStatus
from src.domain.inventory.entities import Inventory, InventoryProcessingMode, InventoryStatus
from tests.support.processing_test_constants import STUB_PRIMARY_MODEL, STUB_PRIMARY_PROVIDER


class FixedClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


class StubInventoryRepo(InventoryRepository):
    def __init__(self) -> None:
        self._store: dict[str, Inventory] = {}

    def save(self, inventory: Inventory) -> None:
        self._store[inventory.id] = inventory

    def get_by_id(self, inventory_id: str):
        return self._store.get(inventory_id)

    def list_all(self):
        return list(self._store.values())


class StubOperationalResolver:
    def resolve(self, settings: Any) -> OperationalPrimaryExecutionConfig:
        _ = settings
        return OperationalPrimaryExecutionConfig(
            provider_name=STUB_PRIMARY_PROVIDER,
            model_name=STUB_PRIMARY_MODEL,
            prompt_key="global_v21",
            prompt_version=None,
        )


def _dummy_settings() -> object:
    return object()


class StubClientRepo(ClientRepository):
    def __init__(self, clients: list[Client] | None = None) -> None:
        self._store = {c.id: c for c in (clients or [])}

    def save(self, client: Client) -> None:
        self._store[client.id] = client

    def get_by_id(self, client_id: str) -> Client | None:
        return self._store.get(client_id)

    def list_all(self):
        return list(self._store.values())


def _active_client(now: datetime, client_id: str = "client-1") -> Client:
    return Client(
        id=client_id,
        name="Retail A",
        status=ClientStatus.ACTIVE,
        created_at=now,
        updated_at=now,
    )


def test_create_inventory_production_snapshots_operational_config() -> None:
    repo = StubInventoryRepo()
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    clock = FixedClock(now)
    client = _active_client(now)
    use_case = CreateInventoryUseCase(
        inventory_repo=repo,
        client_repo=StubClientRepo([client]),
        clock=clock,
        operational_resolver=StubOperationalResolver(),
        settings_loader=_dummy_settings,
    )

    result = use_case.execute(CreateInventoryCommand(name="Warehouse A", client_id=client.id))

    assert result.name == "Warehouse A"
    assert result.status == InventoryStatus.DRAFT
    assert result.processing_mode == InventoryProcessingMode.PRODUCTION
    assert result.primary_provider_name == STUB_PRIMARY_PROVIDER
    assert result.primary_model_name == STUB_PRIMARY_MODEL
    assert result.primary_prompt_key == "global_v21"
    assert result.created_at == now
    assert result.updated_at == now
    assert result.client_id == client.id
    assert repo.get_by_id(result.id) == result
    assert len(repo.list_all()) == 1


def test_create_inventory_test_leaves_primary_fields_null() -> None:
    repo = StubInventoryRepo()
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    clock = FixedClock(now)
    client = _active_client(now, client_id="c-test")
    use_case = CreateInventoryUseCase(
        inventory_repo=repo,
        client_repo=StubClientRepo([client]),
        clock=clock,
        operational_resolver=StubOperationalResolver(),
        settings_loader=_dummy_settings,
    )

    result = use_case.execute(
        CreateInventoryCommand(
            name="Lab",
            processing_mode=InventoryProcessingMode.TEST,
            client_id=client.id,
        )
    )

    assert result.processing_mode == InventoryProcessingMode.TEST
    assert result.primary_provider_name is None
    assert result.primary_model_name is None
    assert result.primary_prompt_key is None
    assert result.primary_prompt_version is None
    assert result.client_id == client.id


def test_create_inventory_with_blank_client_id_after_strip_raises_value_error() -> None:
    repo = StubInventoryRepo()
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    use_case = CreateInventoryUseCase(
        inventory_repo=repo,
        client_repo=StubClientRepo(),
        clock=FixedClock(now),
        operational_resolver=StubOperationalResolver(),
        settings_loader=_dummy_settings,
    )

    with pytest.raises(ValueError, match="client_id must not be empty"):
        use_case.execute(CreateInventoryCommand(name="Warehouse B", client_id="   "))


def test_create_inventory_with_valid_client_id_persists_association() -> None:
    repo = StubInventoryRepo()
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    client = Client(
        id="client-1",
        name="Retail A",
        status=ClientStatus.ACTIVE,
        created_at=now,
        updated_at=now,
    )
    use_case = CreateInventoryUseCase(
        inventory_repo=repo,
        client_repo=StubClientRepo([client]),
        clock=FixedClock(now),
        operational_resolver=StubOperationalResolver(),
        settings_loader=_dummy_settings,
    )

    result = use_case.execute(CreateInventoryCommand(name="Warehouse C", client_id="client-1"))
    assert result.client_id == "client-1"
    assert repo.get_by_id(result.id) == result


def test_create_inventory_with_invalid_client_id_raises_client_not_found() -> None:
    repo = StubInventoryRepo()
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    use_case = CreateInventoryUseCase(
        inventory_repo=repo,
        client_repo=StubClientRepo(),
        clock=FixedClock(now),
        operational_resolver=StubOperationalResolver(),
        settings_loader=_dummy_settings,
    )

    with pytest.raises(ClientNotFoundError):
        use_case.execute(CreateInventoryCommand(name="Warehouse D", client_id="missing-client"))
