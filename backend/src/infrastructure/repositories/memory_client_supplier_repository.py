"""In-memory implementation of ClientSupplierRepository — Phase A2 foundation."""

from __future__ import annotations

from collections.abc import Sequence

from src.application.ports.repositories import ClientSupplierRepository
from src.domain.client_supplier.entities import ClientSupplier


class MemoryClientSupplierRepository(ClientSupplierRepository):
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

    def list_by_client(self, client_id: str) -> Sequence[ClientSupplier]:
        rows = [s for s in self._store.values() if s.client_id == client_id]
        return sorted(rows, key=lambda s: s.created_at, reverse=True)

