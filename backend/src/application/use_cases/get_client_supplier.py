"""GetClientSupplier use case — Phase A2 foundation."""

from __future__ import annotations

from src.application.errors import ClientNotFoundError, ClientSupplierNotFoundError
from src.application.ports.repositories import ClientRepository, ClientSupplierRepository
from src.domain.client_supplier.entities import ClientSupplier


class GetClientSupplierUseCase:
    def __init__(
        self,
        client_repo: ClientRepository,
        client_supplier_repo: ClientSupplierRepository,
    ) -> None:
        self._client_repo = client_repo
        self._client_supplier_repo = client_supplier_repo

    def execute(self, client_id: str, supplier_id: str) -> ClientSupplier:
        client = self._client_repo.get_by_id(client_id)
        if client is None:
            raise ClientNotFoundError(f"Client not found: {client_id}")

        supplier = self._client_supplier_repo.get_by_id(supplier_id)
        if supplier is None or supplier.client_id != client_id:
            raise ClientSupplierNotFoundError(
                f"Client supplier not found in client scope: client_id={client_id} supplier_id={supplier_id}"
            )
        return supplier

