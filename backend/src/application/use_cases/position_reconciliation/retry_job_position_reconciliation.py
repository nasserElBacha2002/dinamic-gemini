"""Explicitly retry Phase 4 reconciliation with a new revision."""

from __future__ import annotations

from src.application.use_cases.position_reconciliation.reconcile_job_positions import (
    ReconcileJobPositionsCommand,
    ReconcileJobPositionsResult,
    ReconcileJobPositionsUseCase,
)


class RetryJobPositionReconciliationUseCase:
    def __init__(self, reconcile: ReconcileJobPositionsUseCase) -> None:
        self._reconcile = reconcile

    def execute(self, command: ReconcileJobPositionsCommand) -> ReconcileJobPositionsResult:
        return self._reconcile.execute(
            ReconcileJobPositionsCommand(
                inventory_id=command.inventory_id,
                job_id=command.job_id,
                principal=command.principal,
                force_new_revision=True,
            )
        )
