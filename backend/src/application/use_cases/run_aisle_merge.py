from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from src.application.errors import (
    AisleNotFoundError,
    InventoryNotFoundError,
    MergeJobScopeAmbiguousError,
)
from src.application.ports.repositories import (
    AisleRepository,
    InventoryRepository,
    RawLabelRepository,
)
from src.application.use_cases.recompute_consolidated_counts import (
    RecomputeConsolidatedCountsCommand,
    RecomputeConsolidatedCountsResult,
    RecomputeConsolidatedCountsUseCase,
    RecomputeJobScope,
)
from src.domain.labels.entities import RawLabel


@dataclass
class RunAisleMergeCommand:
    inventory_id: str
    aisle_id: str
    #: When set, recompute only this inventory job's slice (Phase 1 manual merge).
    job_id: Optional[str] = None


def _resolve_merge_job_scope(
    labels: Sequence[RawLabel],
    explicit_job_id: Optional[str],
) -> RecomputeJobScope:
    """Pick recompute scope for manual merge: never default to aisle-wide ``all`` when ambiguous."""
    if explicit_job_id is not None:
        return explicit_job_id

    non_null = {lb.job_id for lb in labels if lb.job_id}
    null_present = any(lb.job_id is None for lb in labels)

    if len(non_null) > 1:
        raise MergeJobScopeAmbiguousError(
            "Aisle has raw labels from more than one inventory job; pass job_id to merge one run."
        )
    if len(non_null) == 1 and null_present:
        raise MergeJobScopeAmbiguousError(
            "Aisle mixes legacy (null job_id) and job-scoped raw labels; pass job_id to merge one run."
        )
    if len(non_null) == 1:
        return next(iter(non_null))
    return "legacy_null"


class RunAisleMergeUseCase:
    """Execute merge/consolidation as an explicit manual post-process operation."""

    def __init__(
        self,
        inventory_repo: InventoryRepository,
        aisle_repo: AisleRepository,
        raw_label_repo: RawLabelRepository,
        recompute_use_case: RecomputeConsolidatedCountsUseCase,
    ) -> None:
        self._inventory_repo = inventory_repo
        self._aisle_repo = aisle_repo
        self._raw_label_repo = raw_label_repo
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
        raw_labels = list(
            self._raw_label_repo.list_for_scope(command.inventory_id, command.aisle_id, job_id="all")
        )
        job_scope = _resolve_merge_job_scope(raw_labels, command.job_id)

        return self._recompute.execute(
            RecomputeConsolidatedCountsCommand(
                inventory_id=command.inventory_id,
                aisle_id=command.aisle_id,
                apply_to_product_records=True,
                job_scope=job_scope,
            )
        )
