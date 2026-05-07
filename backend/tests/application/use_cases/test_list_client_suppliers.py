"""Tests for ListClientSuppliersUseCase."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.application.errors import ClientNotFoundError
from src.application.ports.repositories import ClientRepository, ClientSupplierRepository
from src.application.use_cases.list_client_suppliers import ListClientSuppliersUseCase
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
    def __init__(self, suppliers: list[ClientSupplier]) -> None:
        self._store = {s.id: s for s in suppliers}

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


def test_list_client_suppliers_for_client() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    client_repo = StubClientRepo()
    client_repo.save(Client("c1", "A", ClientStatus.ACTIVE, now, now))
    suppliers = [
        ClientSupplier("s1", "c1", "One", ClientSupplierStatus.ACTIVE, now, now),
        ClientSupplier("s2", "c2", "Two", ClientSupplierStatus.ACTIVE, now, now),
    ]
    use_case = ListClientSuppliersUseCase(
        client_repo=client_repo,
        client_supplier_repo=StubClientSupplierRepo(suppliers),
    )
    result = use_case.execute("c1")
    assert [s.id for s in result] == ["s1"]


def test_list_client_suppliers_missing_client_raises() -> None:
    use_case = ListClientSuppliersUseCase(
        client_repo=StubClientRepo(),
        client_supplier_repo=StubClientSupplierRepo([]),
    )
    with pytest.raises(ClientNotFoundError):
        use_case.execute("missing")

