"""ListClientSuppliers use case — Phase A2 foundation."""

from __future__ import annotations

from collections.abc import Sequence

from src.application.errors import ClientNotFoundError
from src.application.ports.repositories import ClientRepository, ClientSupplierRepository
from src.domain.client_supplier.entities import ClientSupplier


class ListClientSuppliersUseCase:
    def __init__(
        self,
        client_repo: ClientRepository,
        client_supplier_repo: ClientSupplierRepository,
    ) -> None:
        self._client_repo = client_repo
        self._client_supplier_repo = client_supplier_repo

    def execute(self, client_id: str) -> Sequence[ClientSupplier]:
        client = self._client_repo.get_by_id(client_id)
        if client is None:
            raise ClientNotFoundError(f"Client not found: {client_id}")
        return self._client_supplier_repo.list_by_client(client_id)

