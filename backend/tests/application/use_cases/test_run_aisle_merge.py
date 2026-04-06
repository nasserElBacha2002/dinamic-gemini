from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from src.application.errors import (
    AisleNotFoundError,
    InventoryNotFoundError,
    MergeJobScopeAmbiguousError,
)
from src.application.use_cases.recompute_consolidated_counts import RecomputeConsolidatedCountsResult
from src.application.use_cases.run_aisle_merge import (
    RunAisleMergeCommand,
    RunAisleMergeUseCase,
)
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.domain.labels.entities import RawLabel


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


@dataclass
class _StubRawLabelRepo:
    labels: list[RawLabel] = field(default_factory=list)

    def save_many(self, labels):  # pragma: no cover - merge does not write
        pass

    def list_for_scope(self, inventory_id: str, aisle_id: str, *, job_id: str = "all"):
        assert inventory_id == "inv-1" and aisle_id == "aisle-1"
        assert job_id == "all"
        return list(self.labels)


def _aisle_inv(now: datetime) -> tuple[Inventory, Aisle]:
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
    return inventory, aisle


def _raw(now: datetime, job_id: str | None, rid: str = "r1") -> RawLabel:
    return RawLabel(
        id=rid,
        inventory_id="inv-1",
        aisle_id="aisle-1",
        position_id="p1",
        evidence_id="e1",
        group_key="g1",
        provider="p",
        source_type="hybrid_report",
        source_reference="ref",
        sku_raw="S",
        sku_candidate="S",
        product_name_raw="N",
        detected_text="S",
        confidence=0.9,
        metadata={},
        created_at=now,
        job_id=job_id,
    )


def test_run_aisle_merge_uses_authoritative_apply_mode_and_legacy_scope_when_empty() -> None:
    now = datetime.now(timezone.utc)
    inventory, aisle = _aisle_inv(now)
    recompute = _StubRecomputeUseCase()
    use_case = RunAisleMergeUseCase(
        inventory_repo=_InventoryRepo(inventory),
        aisle_repo=_AisleRepo(aisle),
        raw_label_repo=_StubRawLabelRepo(labels=[]),
        recompute_use_case=recompute,
    )

    result = use_case.execute(RunAisleMergeCommand(inventory_id="inv-1", aisle_id="aisle-1"))

    assert result.product_records_updated == 1
    assert recompute.last_command is not None
    assert recompute.last_command.inventory_id == "inv-1"
    assert recompute.last_command.aisle_id == "aisle-1"
    assert recompute.last_command.apply_to_product_records is True
    assert recompute.last_command.job_scope == "legacy_null"


def test_run_aisle_merge_scopes_to_single_job_when_only_that_job_present() -> None:
    now = datetime.now(timezone.utc)
    inventory, aisle = _aisle_inv(now)
    recompute = _StubRecomputeUseCase()
    use_case = RunAisleMergeUseCase(
        inventory_repo=_InventoryRepo(inventory),
        aisle_repo=_AisleRepo(aisle),
        raw_label_repo=_StubRawLabelRepo(labels=[_raw(now, "job-a")]),
        recompute_use_case=recompute,
    )
    use_case.execute(RunAisleMergeCommand(inventory_id="inv-1", aisle_id="aisle-1"))
    assert recompute.last_command.job_scope == "job-a"


def test_run_aisle_merge_ambiguous_when_multiple_jobs() -> None:
    now = datetime.now(timezone.utc)
    inventory, aisle = _aisle_inv(now)
    use_case = RunAisleMergeUseCase(
        inventory_repo=_InventoryRepo(inventory),
        aisle_repo=_AisleRepo(aisle),
        raw_label_repo=_StubRawLabelRepo(
            labels=[_raw(now, "j1", "r1"), _raw(now, "j2", "r2")]
        ),
        recompute_use_case=_StubRecomputeUseCase(),
    )
    try:
        use_case.execute(RunAisleMergeCommand(inventory_id="inv-1", aisle_id="aisle-1"))
        assert False, "expected MergeJobScopeAmbiguousError"
    except MergeJobScopeAmbiguousError:
        pass


def test_run_aisle_merge_explicit_job_id_allows_multi_job_aisle() -> None:
    now = datetime.now(timezone.utc)
    inventory, aisle = _aisle_inv(now)
    recompute = _StubRecomputeUseCase()
    use_case = RunAisleMergeUseCase(
        inventory_repo=_InventoryRepo(inventory),
        aisle_repo=_AisleRepo(aisle),
        raw_label_repo=_StubRawLabelRepo(
            labels=[_raw(now, "j1", "r1"), _raw(now, "j2", "r2")]
        ),
        recompute_use_case=recompute,
    )
    use_case.execute(
        RunAisleMergeCommand(inventory_id="inv-1", aisle_id="aisle-1", job_id="j2")
    )
    assert recompute.last_command.job_scope == "j2"


def test_run_aisle_merge_ambiguous_mixed_legacy_and_job_scoped() -> None:
    now = datetime.now(timezone.utc)
    inventory, aisle = _aisle_inv(now)
    use_case = RunAisleMergeUseCase(
        inventory_repo=_InventoryRepo(inventory),
        aisle_repo=_AisleRepo(aisle),
        raw_label_repo=_StubRawLabelRepo(
            labels=[_raw(now, None, "r0"), _raw(now, "j1", "r1")]
        ),
        recompute_use_case=_StubRecomputeUseCase(),
    )
    try:
        use_case.execute(RunAisleMergeCommand(inventory_id="inv-1", aisle_id="aisle-1"))
        assert False, "expected MergeJobScopeAmbiguousError"
    except MergeJobScopeAmbiguousError:
        pass


def test_run_aisle_merge_raises_for_missing_inventory() -> None:
    use_case = RunAisleMergeUseCase(
        inventory_repo=_InventoryRepo(None),
        aisle_repo=_AisleRepo(None),
        raw_label_repo=_StubRawLabelRepo(),
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
        raw_label_repo=_StubRawLabelRepo(),
        recompute_use_case=_StubRecomputeUseCase(),
    )

    try:
        use_case.execute(RunAisleMergeCommand(inventory_id="inv-1", aisle_id="aisle-1"))
        assert False, "expected AisleNotFoundError"
    except AisleNotFoundError:
        pass
