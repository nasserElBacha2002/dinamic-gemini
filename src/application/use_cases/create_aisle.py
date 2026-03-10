"""
CreateAisle use case — v3.0 (Épica 3).

Creates an aisle in an inventory. Fails if inventory does not exist or code is duplicate within that inventory.
Raises application exceptions for API to map to 404/409.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from src.application.ports.clock import Clock
from src.application.ports.repositories import AisleRepository, InventoryRepository
from src.domain.aisle.entities import Aisle, AisleStatus


class InventoryNotFoundError(Exception):
    """Raised when the parent inventory does not exist."""


class DuplicateAisleCodeError(Exception):
    """Raised when an aisle with the same code already exists in the inventory."""


@dataclass
class CreateAisleCommand:
    inventory_id: str
    code: str


class CreateAisleUseCase:
    def __init__(
        self,
        inventory_repo: InventoryRepository,
        aisle_repo: AisleRepository,
        clock: Clock,
    ) -> None:
        self._inventory_repo = inventory_repo
        self._aisle_repo = aisle_repo
        self._clock = clock

    def execute(self, command: CreateAisleCommand) -> Aisle:
        code = (command.code or "").strip()
        inventory = self._inventory_repo.get_by_id(command.inventory_id)
        if inventory is None:
            raise InventoryNotFoundError(f"Inventory not found: {command.inventory_id}")

        existing = self._aisle_repo.get_by_inventory_and_code(command.inventory_id, code)
        if existing is not None:
            raise DuplicateAisleCodeError(
                f"An aisle with code {code!r} already exists in this inventory"
            )

        now = self._clock.now()
        aisle = Aisle(
            id=str(uuid4()),
            inventory_id=command.inventory_id,
            code=code,
            status=AisleStatus.CREATED,
            created_at=now,
            updated_at=now,
        )
        self._aisle_repo.save(aisle)
        return aisle
