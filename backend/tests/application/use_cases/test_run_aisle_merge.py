from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import pytest

from src.application.errors import (
    AisleNotFoundError,
    InventoryNotFoundError,
    JobDoesNotBelongToAisleError,
    JobNotFoundError,
)
from src.application.use_cases.recompute_consolidated_counts import (
    RecomputeConsolidatedCountsResult,
)
from src.application.use_cases.run_aisle_merge import (
    RunAisleMergeCommand,
    RunAisleMergeUseCase,
)
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.domain.jobs.entities import Job, JobStatus


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


@dataclass
class _JobRepo:
    """Minimal stub: only ``get_by_id`` is used by ``RunAisleMergeUseCase``."""

    jobs: dict[str, Job] = field(default_factory=dict)

    def get_by_id(self, job_id: str):
        return self.jobs.get(job_id)


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


def _process_aisle_job(now: datetime, job_id: str, *, aisle_id: str = "aisle-1") -> Job:
    return Job(
        id=job_id,
        target_type="aisle",
        target_id=aisle_id,
        job_type="process_aisle",
        status=JobStatus.SUCCEEDED,
        payload_json={},
        created_at=now,
        updated_at=now,
    )


def test_run_aisle_merge_legacy_job_id_delegates_with_legacy_null_scope() -> None:
    now = datetime.now(timezone.utc)
    inventory, aisle = _aisle_inv(now)
    recompute = _StubRecomputeUseCase()
    use_case = RunAisleMergeUseCase(
        inventory_repo=_InventoryRepo(inventory),
        aisle_repo=_AisleRepo(aisle),
        job_repo=_JobRepo(),
        recompute_use_case=recompute,
    )

    result = use_case.execute(
        RunAisleMergeCommand(
            inventory_id="inv-1",
            aisle_id="aisle-1",
            job_id="legacy",
        )
    )

    assert result.product_records_updated == 1
    assert recompute.last_command is not None
    assert recompute.last_command.inventory_id == "inv-1"
    assert recompute.last_command.aisle_id == "aisle-1"
    assert recompute.last_command.apply_to_product_records is True
    assert recompute.last_command.job_scope == "legacy_null"


def test_run_aisle_merge_legacy_is_case_insensitive() -> None:
    now = datetime.now(timezone.utc)
    inventory, aisle = _aisle_inv(now)
    recompute = _StubRecomputeUseCase()
    use_case = RunAisleMergeUseCase(
        inventory_repo=_InventoryRepo(inventory),
        aisle_repo=_AisleRepo(aisle),
        job_repo=_JobRepo(),
        recompute_use_case=recompute,
    )
    use_case.execute(
        RunAisleMergeCommand(
            inventory_id="inv-1",
            aisle_id="aisle-1",
            job_id="LEGACY",
        )
    )
    assert recompute.last_command.job_scope == "legacy_null"


def test_run_aisle_merge_non_legacy_loads_job_and_passes_job_id_scope() -> None:
    now = datetime.now(timezone.utc)
    inventory, aisle = _aisle_inv(now)
    recompute = _StubRecomputeUseCase()
    job = _process_aisle_job(now, "job-a")
    use_case = RunAisleMergeUseCase(
        inventory_repo=_InventoryRepo(inventory),
        aisle_repo=_AisleRepo(aisle),
        job_repo=_JobRepo(jobs={"job-a": job}),
        recompute_use_case=recompute,
    )
    use_case.execute(
        RunAisleMergeCommand(
            inventory_id="inv-1",
            aisle_id="aisle-1",
            job_id="job-a",
        )
    )
    assert recompute.last_command.job_scope == "job-a"


def test_run_aisle_merge_explicit_job_id_selects_that_job_when_multiple_exist() -> None:
    now = datetime.now(timezone.utc)
    inventory, aisle = _aisle_inv(now)
    recompute = _StubRecomputeUseCase()
    use_case = RunAisleMergeUseCase(
        inventory_repo=_InventoryRepo(inventory),
        aisle_repo=_AisleRepo(aisle),
        job_repo=_JobRepo(
            jobs={
                "j1": _process_aisle_job(now, "j1"),
                "j2": _process_aisle_job(now, "j2"),
            }
        ),
        recompute_use_case=recompute,
    )
    use_case.execute(
        RunAisleMergeCommand(
            inventory_id="inv-1",
            aisle_id="aisle-1",
            job_id="j2",
        )
    )
    assert recompute.last_command.job_scope == "j2"


def test_run_aisle_merge_raises_job_not_found() -> None:
    now = datetime.now(timezone.utc)
    inventory, aisle = _aisle_inv(now)
    use_case = RunAisleMergeUseCase(
        inventory_repo=_InventoryRepo(inventory),
        aisle_repo=_AisleRepo(aisle),
        job_repo=_JobRepo(jobs={}),
        recompute_use_case=_StubRecomputeUseCase(),
    )
    with pytest.raises(JobNotFoundError):
        use_case.execute(
            RunAisleMergeCommand(
                inventory_id="inv-1",
                aisle_id="aisle-1",
                job_id="missing-job",
            )
        )


def test_run_aisle_merge_raises_job_does_not_belong_to_aisle() -> None:
    now = datetime.now(timezone.utc)
    inventory, aisle = _aisle_inv(now)
    other_aisle_job = _process_aisle_job(now, "job-x", aisle_id="other-aisle")
    use_case = RunAisleMergeUseCase(
        inventory_repo=_InventoryRepo(inventory),
        aisle_repo=_AisleRepo(aisle),
        job_repo=_JobRepo(jobs={"job-x": other_aisle_job}),
        recompute_use_case=_StubRecomputeUseCase(),
    )
    with pytest.raises(JobDoesNotBelongToAisleError):
        use_case.execute(
            RunAisleMergeCommand(
                inventory_id="inv-1",
                aisle_id="aisle-1",
                job_id="job-x",
            )
        )


def test_run_aisle_merge_raises_for_missing_inventory() -> None:
    use_case = RunAisleMergeUseCase(
        inventory_repo=_InventoryRepo(None),
        aisle_repo=_AisleRepo(None),
        job_repo=_JobRepo(),
        recompute_use_case=_StubRecomputeUseCase(),
    )
    with pytest.raises(InventoryNotFoundError):
        use_case.execute(
            RunAisleMergeCommand(
                inventory_id="inv-1",
                aisle_id="aisle-1",
                job_id="legacy",
            )
        )


def test_run_aisle_merge_raises_for_aisle_not_in_inventory() -> None:
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
        job_repo=_JobRepo(),
        recompute_use_case=_StubRecomputeUseCase(),
    )
    with pytest.raises(AisleNotFoundError):
        use_case.execute(
            RunAisleMergeCommand(
                inventory_id="inv-1",
                aisle_id="aisle-1",
                job_id="legacy",
            )
        )


def test_run_aisle_merge_raises_value_error_when_job_id_blank() -> None:
    now = datetime.now(timezone.utc)
    inventory, aisle = _aisle_inv(now)
    use_case = RunAisleMergeUseCase(
        inventory_repo=_InventoryRepo(inventory),
        aisle_repo=_AisleRepo(aisle),
        job_repo=_JobRepo(),
        recompute_use_case=_StubRecomputeUseCase(),
    )
    with pytest.raises(ValueError, match="job_id is required"):
        use_case.execute(
            RunAisleMergeCommand(
                inventory_id="inv-1",
                aisle_id="aisle-1",
                job_id="   ",
            )
        )
