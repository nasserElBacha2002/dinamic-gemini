"""Read the active Phase 4 reconciliation for a job."""

from __future__ import annotations

from dataclasses import dataclass

from src.application.dto.access_principal import AccessPrincipal
from src.application.ports.position_reconciliation_repository import (
    PositionReconciliationRepository,
)
from src.application.services.inventory_access_policy import InventoryAccessPolicy
from src.domain.position_reconciliation.entities import PositionReconciliation


@dataclass(frozen=True)
class GetJobPositionReconciliationCommand:
    inventory_id: str
    job_id: str
    principal: AccessPrincipal


class GetJobPositionReconciliationUseCase:
    def __init__(
        self,
        *,
        repository: PositionReconciliationRepository,
        access_policy: InventoryAccessPolicy,
    ) -> None:
        self._repository = repository
        self._access = access_policy

    def execute(
        self, command: GetJobPositionReconciliationCommand
    ) -> PositionReconciliation | None:
        self._access.require_inventory(command.inventory_id, command.principal)
        row = self._repository.get_published_by_job(command.job_id)
        if row is None or row.inventory_id != command.inventory_id:
            return None
        return row
