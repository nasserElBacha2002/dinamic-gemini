"""CreateClientSupplier use case — Phase A2 foundation."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from src.application.errors import (
    ClientNotFoundError,
    DuplicateClientSupplierNameError,
    InvalidClientSupplierNameError,
)
from src.application.ports.clock import Clock
from src.application.ports.repositories import ClientRepository, ClientSupplierRepository
from src.domain.client_supplier.entities import ClientSupplier, ClientSupplierStatus


@dataclass
class CreateClientSupplierCommand:
    client_id: str
    name: str
    status: ClientSupplierStatus = ClientSupplierStatus.ACTIVE


class CreateClientSupplierUseCase:
    def __init__(
        self,
        client_repo: ClientRepository,
        client_supplier_repo: ClientSupplierRepository,
        clock: Clock,
    ) -> None:
        self._client_repo = client_repo
        self._client_supplier_repo = client_supplier_repo
        self._clock = clock

    def execute(self, command: CreateClientSupplierCommand) -> ClientSupplier:
        client = self._client_repo.get_by_id(command.client_id)
        if client is None:
            raise ClientNotFoundError(f"Client not found: {command.client_id}")

        name = (command.name or "").strip()
        if not name:
            raise InvalidClientSupplierNameError("Client supplier name is required")

        existing = self._client_supplier_repo.get_by_client_and_name(command.client_id, name)
        if existing is not None:
            raise DuplicateClientSupplierNameError(
                f"Client supplier with name {name!r} already exists for client {command.client_id}"
            )

        now = self._clock.now()
        supplier = ClientSupplier(
            id=str(uuid4()),
            client_id=command.client_id,
            name=name,
            status=command.status,
            created_at=now,
            updated_at=now,
        )
        self._client_supplier_repo.save(supplier)
        return supplier

