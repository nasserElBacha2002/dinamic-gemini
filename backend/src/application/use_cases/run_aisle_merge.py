from __future__ import annotations

from dataclasses import dataclass

from src.application.errors import (
    AisleNotFoundError,
    InventoryNotFoundError,
    JobDoesNotBelongToAisleError,
    JobNotFoundError,
)
from src.application.ports.repositories import AisleRepository, InventoryRepository, JobRepository
from src.application.use_cases.recompute_consolidated_counts import (
    RecomputeConsolidatedCountsCommand,
    RecomputeConsolidatedCountsResult,
    RecomputeConsolidatedCountsUseCase,
    RecomputeJobScope,
)


@dataclass
class RunAisleMergeCommand:
    inventory_id: str
    aisle_id: str
    #: Inventory job id for the run to merge, or the literal ``legacy`` for ``job_id IS NULL`` slice.
    job_id: str


class RunAisleMergeUseCase:
    """Execute merge/consolidation as an explicit manual post-process operation."""

    def __init__(
        self,
        inventory_repo: InventoryRepository,
        aisle_repo: AisleRepository,
        job_repo: JobRepository,
        recompute_use_case: RecomputeConsolidatedCountsUseCase,
    ) -> None:
        self._inventory_repo = inventory_repo
        self._aisle_repo = aisle_repo
        self._job_repo = job_repo
        self._recompute = recompute_use_case

    def execute(self, command: RunAisleMergeCommand) -> RecomputeConsolidatedCountsResult:
        inv = self._inventory_repo.get_by_id(command.inventory_id)
        if inv is None:
            raise InventoryNotFoundError(f"Inventory not found: {command.inventory_id}")
        aisle = self._aisle_repo.get_by_id(command.aisle_id)
        if aisle is None or aisle.inventory_id != command.inventory_id:
            raise AisleNotFoundError(
                f"Aisle {command.aisle_id} does not belong to inventory {command.inventory_id}"
            )
        spec = (command.job_id or "").strip()
        if not spec:
            raise ValueError("job_id is required (inventory job id or the literal 'legacy').")
        if spec.lower() == "legacy":
            job_scope: RecomputeJobScope = "legacy_null"
        else:
            job = self._job_repo.get_by_id(spec)
            if job is None:
                raise JobNotFoundError(f"Job not found: {spec}")
            if job.target_type != "aisle" or job.target_id != command.aisle_id:
                raise JobDoesNotBelongToAisleError(
                    f"Job {spec} does not belong to aisle {command.aisle_id}"
                )
            job_scope = spec

        return self._recompute.execute(
            RecomputeConsolidatedCountsCommand(
                inventory_id=command.inventory_id,
                aisle_id=command.aisle_id,
                apply_to_product_records=True,
                job_scope=job_scope,
            )
        )
