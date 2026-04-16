from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from src.application.errors import InventoryNotFoundError
from src.application.services.aisle_inventory_scope import require_aisle_scoped_to_inventory
from src.application.ports.repositories import (
    AisleRepository,
    FinalCountRepository,
    InventoryRepository,
)
from src.application.services.result_context_resolver import ResultContextResolver
from src.domain.labels.entities import FinalCountRecord


@dataclass
class GetAisleMergeResultsCommand:
    inventory_id: str
    aisle_id: str
    job_id: Optional[str] = None


@dataclass(frozen=True)
class GetAisleMergeResultsResult:
    records: Sequence[FinalCountRecord]
    resolved_job_id: Optional[str]
    result_context_source: str


class GetAisleMergeResultsUseCase:
    """Final_count rows for one resolved result context (Phase 2 — no aisle-wide ``all`` slice)."""

    def __init__(
        self,
        inventory_repo: InventoryRepository,
        aisle_repo: AisleRepository,
        final_count_repo: FinalCountRepository,
        result_context_resolver: ResultContextResolver,
    ) -> None:
        self._inventory_repo = inventory_repo
        self._aisle_repo = aisle_repo
        self._final_count_repo = final_count_repo
        self._resolver = result_context_resolver

    def execute(self, command: GetAisleMergeResultsCommand) -> GetAisleMergeResultsResult:
        inv = self._inventory_repo.get_by_id(command.inventory_id)
        if inv is None:
            raise InventoryNotFoundError(f"Inventory not found: {command.inventory_id}")
        aisle = require_aisle_scoped_to_inventory(
            self._aisle_repo,
            inventory_id=command.inventory_id,
            aisle_id=command.aisle_id,
            detail_style="merged",
        )
        ctx = self._resolver.resolve(aisle=aisle, explicit_job_id=command.job_id)
        records = self._final_count_repo.list_for_scope(
            command.inventory_id, command.aisle_id, job_id=ctx.job_id_for_slice
        )
        return GetAisleMergeResultsResult(
            records=records,
            resolved_job_id=ctx.job_id_for_slice,
            result_context_source=ctx.source,
        )
