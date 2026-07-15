"""ActivateAisle use case — re-activate a soft-deactivated aisle."""

from __future__ import annotations

from dataclasses import dataclass

from src.application.ports.clock import Clock
from src.application.ports.repositories import AisleRepository
from src.application.services.aisle_inventory_scope import require_aisle_scoped_to_inventory
from src.domain.aisle.entities import Aisle


@dataclass
class ActivateAisleCommand:
    inventory_id: str
    aisle_id: str


class ActivateAisleUseCase:
    def __init__(
        self,
        aisle_repo: AisleRepository,
        clock: Clock,
    ) -> None:
        self._aisle_repo = aisle_repo
        self._clock = clock

    def execute(self, command: ActivateAisleCommand) -> Aisle:
        aisle = require_aisle_scoped_to_inventory(
            self._aisle_repo,
            inventory_id=command.inventory_id,
            aisle_id=command.aisle_id,
            detail_style="strict",
        )
        if aisle.is_active:
            return aisle

        aisle.activate(self._clock.now())
        self._aisle_repo.save(aisle)
        return aisle
