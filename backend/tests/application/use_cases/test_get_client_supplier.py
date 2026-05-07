"""Tests for GetClientSupplierUseCase."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.application.errors import ClientNotFoundError, ClientSupplierNotFoundError
from src.application.ports.repositories import ClientRepository, ClientSupplierRepository
from src.application.use_cases.get_client_supplier import GetClientSupplierUseCase
from src.domain.client.entities import Client, ClientStatus
from src.domain.client_supplier.entities import ClientSupplier, ClientSupplierStatus


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
        for supplier in self._store.values():
            if supplier.client_id == client_id and supplier.name == name:
                return supplier
        return None

    def list_by_client(self, client_id: str):
        return [s for s in self._store.values() if s.client_id == client_id]


def test_get_client_supplier_success_scoped() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    client_repo = StubClientRepo()
    supplier_repo = StubClientSupplierRepo()
    client_repo.save(Client("c1", "Retail", ClientStatus.ACTIVE, now, now))
    supplier_repo.save(
        ClientSupplier("s1", "c1", "Acme", ClientSupplierStatus.ACTIVE, now, now)
    )
    use_case = GetClientSupplierUseCase(client_repo=client_repo, client_supplier_repo=supplier_repo)

    result = use_case.execute("c1", "s1")
    assert result.id == "s1"


def test_get_client_supplier_missing_client_raises() -> None:
    use_case = GetClientSupplierUseCase(
        client_repo=StubClientRepo(),
        client_supplier_repo=StubClientSupplierRepo(),
    )
    with pytest.raises(ClientNotFoundError):
        use_case.execute("missing", "s1")


def test_get_client_supplier_cross_client_access_protected() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    client_repo = StubClientRepo()
    supplier_repo = StubClientSupplierRepo()
    client_repo.save(Client("a", "A", ClientStatus.ACTIVE, now, now))
    client_repo.save(Client("b", "B", ClientStatus.ACTIVE, now, now))
    supplier_repo.save(
        ClientSupplier("s1", "a", "Acme", ClientSupplierStatus.ACTIVE, now, now)
    )
    use_case = GetClientSupplierUseCase(client_repo=client_repo, client_supplier_repo=supplier_repo)

    with pytest.raises(ClientSupplierNotFoundError):
        use_case.execute("b", "s1")


def test_get_client_supplier_missing_id_under_existing_client_raises() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    client_repo = StubClientRepo()
    supplier_repo = StubClientSupplierRepo()
    client_repo.save(Client("c1", "Retail", ClientStatus.ACTIVE, now, now))
    use_case = GetClientSupplierUseCase(client_repo=client_repo, client_supplier_repo=supplier_repo)

    with pytest.raises(ClientSupplierNotFoundError):
        use_case.execute("c1", "missing-supplier-id")

