"""List inventories for a Raspberry device, scoped to one client."""

from __future__ import annotations

from dataclasses import dataclass

from src.application.errors import ClientNotFoundError
from src.application.ports.repositories import ClientRepository, InventoryRepository
from src.domain.inventory.entities import Inventory


@dataclass(frozen=True)
class ListRaspberryInventoriesCommand:
    client_id: str


class ListRaspberryInventoriesUseCase:
    def __init__(
        self,
        *,
        client_repo: ClientRepository,
        inventory_repo: InventoryRepository,
    ) -> None:
        self._client_repo = client_repo
        self._inventory_repo = inventory_repo

    def execute(self, command: ListRaspberryInventoriesCommand) -> tuple[Inventory, ...]:
        client_id = (command.client_id or "").strip()
        if not client_id or self._client_repo.get_by_id(client_id) is None:
            raise ClientNotFoundError(f"Client not found: {client_id}")
        return tuple(self._inventory_repo.list_for_client(client_id))
