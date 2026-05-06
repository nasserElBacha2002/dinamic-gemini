"""
v3.2.3.E4 — Backfill / recompute of legacy aisles.

Batch wrapper around RecomputeConsolidatedCountsUseCase to realign historical
aisles with the consolidated counting model.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from src.application.ports.repositories import AisleRepository, InventoryRepository
from src.application.use_cases.recompute_consolidated_counts import (
    RecomputeConsolidatedCountsCommand,
    RecomputeConsolidatedCountsResult,
    RecomputeConsolidatedCountsUseCase,
)
from src.domain.aisle.entities import Aisle


@dataclass
class BackfillLegacyAislesCommand:
    """
    Describe which aisles should be recomputed.

    At least one of:
    - inventory_id
    - aisle_ids
    - all_aisles
    must be provided.
    """

    inventory_id: str | None = None
    aisle_ids: Sequence[str] | None = None
    all_aisles: bool = False


@dataclass
class BackfillAisleResult:
    inventory_id: str
    aisle_id: str
    success: bool
    raw_count: int = 0
    normalized_count: int = 0
    final_count: int = 0
    product_records_updated: int = 0
    error_message: str | None = None


@dataclass
class BackfillLegacyAislesResult:
    total_aisles_scanned: int
    total_aisles_recomputed: int
    total_successes: int
    total_failures: int
    aisle_results: list[BackfillAisleResult]


class BackfillLegacyAislesUseCase:
    """
    Batch backfill for legacy aisles using the existing consolidated recompute flow.

    Responsibilities:
    - Resolve target aisles from command (inventory_id / aisle_ids / all_aisles).
    - For each aisle, invoke RecomputeConsolidatedCountsUseCase.
    - Collect per-aisle results and an aggregate summary.
    - Isolate failures so one bad aisle does not stop the batch.
    """

    def __init__(
        self,
        inventory_repo: InventoryRepository,
        aisle_repo: AisleRepository,
        recompute_uc: RecomputeConsolidatedCountsUseCase,
    ) -> None:
        self._inventory_repo = inventory_repo
        self._aisle_repo = aisle_repo
        self._recompute_uc = recompute_uc

    def execute(self, command: BackfillLegacyAislesCommand) -> BackfillLegacyAislesResult:
        # Enforce explicit, non-ambiguous targeting mode.
        modes = [
            bool(command.aisle_ids),
            command.inventory_id is not None,
            bool(command.all_aisles),
        ]
        if sum(1 for m in modes if m) == 0:
            raise ValueError(
                "BackfillLegacyAislesCommand requires aisle_ids, inventory_id, or all_aisles=True"
            )
        if sum(1 for m in modes if m) > 1:
            raise ValueError(
                "BackfillLegacyAislesCommand supports exactly one targeting mode: "
                "explicit aisle_ids OR inventory_id OR all_aisles=True"
            )

        aisles, unresolved_aisle_ids = self._resolve_targets(command)

        results: list[BackfillAisleResult] = []
        # Record explicit failures for unresolved aisle IDs (operator intent was to touch them).
        for aid in unresolved_aisle_ids:
            results.append(
                BackfillAisleResult(
                    inventory_id="",
                    aisle_id=aid,
                    success=False,
                    error_message="Aisle not found",
                )
            )

        for aisle in aisles:
            results.append(self._recompute_one(aisle))

        total_scanned = len(results)
        total_successes = sum(1 for r in results if r.success)
        total_failures = sum(1 for r in results if not r.success)
        total_recomputed = total_successes

        return BackfillLegacyAislesResult(
            total_aisles_scanned=total_scanned,
            total_aisles_recomputed=total_recomputed,
            total_successes=total_successes,
            total_failures=total_failures,
            aisle_results=results,
        )

    def _resolve_targets(
        self, command: BackfillLegacyAislesCommand
    ) -> tuple[list[Aisle], list[str]]:
        """
        Resolve target aisles from the command.

        Rules:
        - If aisle_ids is provided → explicit set (fail when not found).
        - Else if inventory_id is provided → all aisles in that inventory.
        - Else if all_aisles is True → all aisles from all inventories.
        - Else → ValueError (no scope specified).
        """
        aisle_ids = list(command.aisle_ids or [])
        have_aisles = bool(aisle_ids)
        have_inventory = command.inventory_id is not None

        aisles: list[Aisle] = []
        unresolved: list[str] = []

        if have_aisles:
            # Explicit aisles; unresolved ids are reported as failures by the caller.
            for aid in aisle_ids:
                aisle = self._aisle_repo.get_by_id(aid)
                if aisle is None:
                    unresolved.append(aid)
                else:
                    aisles.append(aisle)
            return aisles, unresolved

        if have_inventory and not command.all_aisles:
            inv = self._inventory_repo.get_by_id(command.inventory_id or "")
            if inv is None:
                # Invalid inventory id is an explicit configuration error.
                raise ValueError(f"Inventory not found for backfill: {command.inventory_id}")
            aisles = list(self._aisle_repo.list_by_inventory(inv.id))
            return aisles, unresolved

        if command.all_aisles:
            inventories = self._inventory_repo.list_all()
            for inv in inventories:
                for aisle in self._aisle_repo.list_by_inventory(inv.id):
                    aisles.append(aisle)
            return aisles, unresolved

        return aisles, unresolved

    def _recompute_one(self, aisle: Aisle) -> BackfillAisleResult:
        try:
            res: RecomputeConsolidatedCountsResult = self._recompute_uc.execute(
                RecomputeConsolidatedCountsCommand(
                    inventory_id=aisle.inventory_id,
                    aisle_id=aisle.id,
                    apply_to_product_records=True,
                    job_scope="legacy_null",
                )
            )
            return BackfillAisleResult(
                inventory_id=aisle.inventory_id,
                aisle_id=aisle.id,
                success=True,
                raw_count=res.raw_count,
                normalized_count=res.normalized_count,
                final_count=res.final_count,
                product_records_updated=res.product_records_updated,
            )
        except Exception as e:
            return BackfillAisleResult(
                inventory_id=aisle.inventory_id,
                aisle_id=aisle.id,
                success=False,
                error_message=str(e),
            )
