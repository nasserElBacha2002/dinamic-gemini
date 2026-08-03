"""List active assigned or unassigned Phase 4 product results."""

from __future__ import annotations

from dataclasses import dataclass

from src.application.dto.access_principal import AccessPrincipal
from src.application.ports.position_reconciliation_repository import (
    PositionReconciliationRepository,
)
from src.application.services.inventory_access_policy import InventoryAccessPolicy
from src.domain.position_reconciliation.entities import ProductPositionAssignment


@dataclass(frozen=True)
class ListJobPositionAssignmentsCommand:
    inventory_id: str
    job_id: str
    principal: AccessPrincipal
    unassigned_only: bool = False


class ListJobPositionAssignmentsUseCase:
    def __init__(
        self,
        *,
        repository: PositionReconciliationRepository,
        access_policy: InventoryAccessPolicy,
    ) -> None:
        self._repository = repository
        self._access = access_policy

    def execute(
        self, command: ListJobPositionAssignmentsCommand
    ) -> list[ProductPositionAssignment]:
        self._access.require_inventory(command.inventory_id, command.principal)
        rows = (
            self._repository.list_unassigned(command.job_id)
            if command.unassigned_only
            else self._repository.list_active_assignments(command.job_id)
        )
        return [row for row in rows if row.inventory_id == command.inventory_id]
