from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from src.application.errors import AisleNotFoundError, InventoryNotFoundError
from src.application.use_cases.recompute_consolidated_counts import RecomputeConsolidatedCountsResult
from src.application.use_cases.run_aisle_merge import (
    RunAisleMergeCommand,
    RunAisleMergeUseCase,
)
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.inventory.entities import Inventory, InventoryStatus


@dataclass
class _InventoryRepo:
    inventory: Inventory | None

    def get_by_id(self, inventory_id: str):
        return self.inventory if self.inventory and self.inventory.id == inventory_id else None


@dataclass
class _AisleRepo:
    aisle: Aisle | None

    def get_by_id(self, aisle_id: str):
        return self.aisle if self.aisle and self.aisle.id == aisle_id else None


class _StubRecomputeUseCase:
    def __init__(self) -> None:
        self.last_command = None

    def execute(self, command):
        self.last_command = command
        return RecomputeConsolidatedCountsResult(
            raw_count=3,
            normalized_count=1,
            final_count=1,
            product_records_updated=1,
        )


def test_run_aisle_merge_uses_authoritative_apply_mode() -> None:
    now = datetime.now(timezone.utc)
    inventory = Inventory(
        id="inv-1",
        name="Inventory",
        status=InventoryStatus.DRAFT,
        created_at=now,
        updated_at=now,
    )
    aisle = Aisle(
        id="aisle-1",
        inventory_id="inv-1",
        code="A01",
        status=AisleStatus.CREATED,
        created_at=now,
        updated_at=now,
    )
    recompute = _StubRecomputeUseCase()
    use_case = RunAisleMergeUseCase(
        inventory_repo=_InventoryRepo(inventory),
        aisle_repo=_AisleRepo(aisle),
        recompute_use_case=recompute,
    )

    result = use_case.execute(RunAisleMergeCommand(inventory_id="inv-1", aisle_id="aisle-1"))

    assert result.product_records_updated == 1
    assert recompute.last_command is not None
    assert recompute.last_command.inventory_id == "inv-1"
    assert recompute.last_command.aisle_id == "aisle-1"
    assert recompute.last_command.apply_to_product_records is True


def test_run_aisle_merge_raises_for_missing_inventory() -> None:
    use_case = RunAisleMergeUseCase(
        inventory_repo=_InventoryRepo(None),
        aisle_repo=_AisleRepo(None),
        recompute_use_case=_StubRecomputeUseCase(),
    )

    try:
        use_case.execute(RunAisleMergeCommand(inventory_id="inv-1", aisle_id="aisle-1"))
        assert False, "expected InventoryNotFoundError"
    except InventoryNotFoundError:
        pass


def test_run_aisle_merge_raises_for_wrong_aisle_inventory() -> None:
    now = datetime.now(timezone.utc)
    inventory = Inventory(
        id="inv-1",
        name="Inventory",
        status=InventoryStatus.DRAFT,
        created_at=now,
        updated_at=now,
    )
    aisle = Aisle(
        id="aisle-1",
        inventory_id="inv-2",
        code="A01",
        status=AisleStatus.CREATED,
        created_at=now,
        updated_at=now,
    )
    use_case = RunAisleMergeUseCase(
        inventory_repo=_InventoryRepo(inventory),
        aisle_repo=_AisleRepo(aisle),
        recompute_use_case=_StubRecomputeUseCase(),
    )

    try:
        use_case.execute(RunAisleMergeCommand(inventory_id="inv-1", aisle_id="aisle-1"))
        assert False, "expected AisleNotFoundError"
    except AisleNotFoundError:
        pass
