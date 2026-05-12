"""Tests for CreateClientSupplierUseCase."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.application.errors import (
    ClientNotFoundError,
    DuplicateClientSupplierNameError,
    InvalidClientSupplierNameError,
)
from src.application.ports.repositories import ClientRepository, ClientSupplierRepository
from src.application.use_cases.create_client_supplier import (
    CreateClientSupplierCommand,
    CreateClientSupplierUseCase,
)
from src.domain.client.entities import Client, ClientStatus
from src.domain.client_supplier.entities import ClientSupplier, ClientSupplierStatus


class FixedClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


class StubClientRepo(ClientRepository):
    def __init__(self) -> None:
        self._store: dict[str, Client] = {}

    def save(self, client: Client) -> None:
        self._store[client.id] = client

    def get_by_id(self, client_id: str) -> Client | None:
        return self._store.get(client_id)

    def list_all(self):
        return list(self._store.values())


class StubClientSupplierRepo(ClientSupplierRepository):
    def __init__(self) -> None:
        self._store: dict[str, ClientSupplier] = {}

    def save(self, supplier: ClientSupplier) -> None:
        self._store[supplier.id] = supplier

    def get_by_id(self, supplier_id: str) -> ClientSupplier | None:
        return self._store.get(supplier_id)

    def get_by_client_and_name(self, client_id: str, name: str) -> ClientSupplier | None:
        target = name.strip().lower()
        for supplier in self._store.values():
            if supplier.client_id == client_id and supplier.name.strip().lower() == target:
                return supplier
        return None

    def list_by_client(self, client_id: str):
        return [s for s in self._store.values() if s.client_id == client_id]


def test_create_client_supplier_success_for_existing_client() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    client_repo = StubClientRepo()
    supplier_repo = StubClientSupplierRepo()
    client_repo.save(
        Client(
            id="client-1",
            name="Retail A",
            status=ClientStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
    )
    use_case = CreateClientSupplierUseCase(
        client_repo=client_repo,
        client_supplier_repo=supplier_repo,
        clock=FixedClock(now),
    )

    result = use_case.execute(CreateClientSupplierCommand(client_id="client-1", name="Acme"))

    assert result.client_id == "client-1"
    assert result.name == "Acme"
    assert result.status == ClientSupplierStatus.ACTIVE
    assert supplier_repo.get_by_id(result.id) == result


def test_create_client_supplier_validation_failure_when_name_empty() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    client_repo = StubClientRepo()
    supplier_repo = StubClientSupplierRepo()
    client_repo.save(
        Client(
            id="client-1",
            name="Retail A",
            status=ClientStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
    )
    use_case = CreateClientSupplierUseCase(
        client_repo=client_repo,
        client_supplier_repo=supplier_repo,
        clock=FixedClock(now),
    )

    with pytest.raises(InvalidClientSupplierNameError, match="Client supplier name is required"):
        use_case.execute(CreateClientSupplierCommand(client_id="client-1", name="   "))


def test_create_client_supplier_missing_client_raises_not_found() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    use_case = CreateClientSupplierUseCase(
        client_repo=StubClientRepo(),
        client_supplier_repo=StubClientSupplierRepo(),
        clock=FixedClock(now),
    )

    with pytest.raises(ClientNotFoundError):
        use_case.execute(CreateClientSupplierCommand(client_id="missing", name="Acme"))


def test_create_client_supplier_duplicate_name_same_client_rejected() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    client_repo = StubClientRepo()
    supplier_repo = StubClientSupplierRepo()
    client_repo.save(
        Client(
            id="client-1",
            name="Retail A",
            status=ClientStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
    )
    supplier_repo.save(
        ClientSupplier(
            id="supp-1",
            client_id="client-1",
            name="Acme",
            status=ClientSupplierStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
    )
    use_case = CreateClientSupplierUseCase(
        client_repo=client_repo,
        client_supplier_repo=supplier_repo,
        clock=FixedClock(now),
    )

    with pytest.raises(DuplicateClientSupplierNameError):
        use_case.execute(CreateClientSupplierCommand(client_id="client-1", name="Acme"))


def test_create_client_supplier_same_name_different_clients_allowed() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    client_repo = StubClientRepo()
    supplier_repo = StubClientSupplierRepo()
    client_repo.save(
        Client(
            id="client-a",
            name="A",
            status=ClientStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
    )
    client_repo.save(
        Client(
            id="client-b",
            name="B",
            status=ClientStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
    )
    supplier_repo.save(
        ClientSupplier(
            id="supp-a",
            client_id="client-a",
            name="Shared",
            status=ClientSupplierStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
    )
    use_case = CreateClientSupplierUseCase(
        client_repo=client_repo,
        client_supplier_repo=supplier_repo,
        clock=FixedClock(now),
    )

    created = use_case.execute(CreateClientSupplierCommand(client_id="client-b", name="Shared"))
    assert created.client_id == "client-b"

