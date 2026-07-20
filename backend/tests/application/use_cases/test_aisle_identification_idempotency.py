"""Idempotent replay for StartAisleProcessingUseCase returns the original job snapshot directly.

Regression coverage: ``_find_job_by_idempotency_key`` now returns the matching ``Job`` object
instead of a job id that gets re-fetched (and previously could fall back to hardcoded
LEGACY_LLM/SYSTEM_DEFAULT values if the re-fetch missed). Replays must always reflect exactly
what was persisted on the original job — even if the aisle's configured mode changes afterward.
"""

from __future__ import annotations

from datetime import datetime, timezone

from src.application.services.inventory_status_reconciler import InventoryStatusReconciler
from src.application.use_cases.aisles.start_aisle_processing import (
    StartAisleProcessingCommand,
    StartAisleProcessingUseCase,
)
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.aisle_identification.modes import AisleIdentificationMode
from src.domain.inventory.entities import Inventory, InventoryStatus
from tests.application.use_cases.test_aisle_processing import (
    FixedClock,
    StubAisleRepo,
    StubInventoryRepo,
    StubJobRepo,
    StubWorkerLaunchService,
    _stub_asset_repo_with_one_photo,
    make_launch_service,
    make_stale_reconciler,
)


def _build_use_case(
    *, inventory: Inventory, aisle: Aisle
) -> tuple[StartAisleProcessingUseCase, StubJobRepo, StubAisleRepo]:
    inv_repo = StubInventoryRepo([inventory])
    aisle_repo = StubAisleRepo()
    aisle_repo.save(aisle)
    job_repo = StubJobRepo()
    clock = FixedClock(aisle.created_at)
    reconciler = InventoryStatusReconciler(inv_repo, aisle_repo, clock)
    use_case = StartAisleProcessingUseCase(
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        asset_repo=_stub_asset_repo_with_one_photo(aisle_id=aisle.id),
        job_repo=job_repo,
        launch_service=make_launch_service(
            aisle_repo=aisle_repo,
            job_repo=job_repo,
            worker_launch_service=StubWorkerLaunchService(),
            clock=clock,
            reconciler=reconciler,
        ),
        stale_reconciler=make_stale_reconciler(job_repo, clock),
    )
    return use_case, job_repo, aisle_repo


def test_idempotent_replay_returns_original_job_snapshot() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    inv = Inventory("inv1", "W", InventoryStatus.DRAFT, now, now)
    aisle = Aisle(
        "a1",
        "inv1",
        "A01",
        AisleStatus.CREATED,
        now,
        now,
        identification_mode=AisleIdentificationMode.INTERNAL_OCR,
    )
    use_case, job_repo, _ = _build_use_case(inventory=inv, aisle=aisle)

    first = use_case.execute(
        StartAisleProcessingCommand(
            inventory_id="inv1", aisle_id="a1", idempotency_key="req-key-1"
        )
    )
    replay = use_case.execute(
        StartAisleProcessingCommand(
            inventory_id="inv1", aisle_id="a1", idempotency_key="req-key-1"
        )
    )

    assert replay.job_id == first.job_id
    assert replay.identification_mode == first.identification_mode == "INTERNAL_OCR"
    assert replay.identification_mode_source == first.identification_mode_source == "AISLE"
    assert replay.execution_strategy == first.execution_strategy
    assert replay.configuration_snapshot_version == first.configuration_snapshot_version
    # Only one job was ever created for this idempotency key.
    assert len(job_repo.list_jobs_for_target("aisle", "a1", limit=100)) == 1


def test_idempotent_replay_unaffected_by_later_aisle_mutation() -> None:
    """Changing the aisle's configured mode after the first job must not change the replay result."""
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    inv = Inventory("inv1", "W", InventoryStatus.DRAFT, now, now)
    aisle = Aisle(
        "a1",
        "inv1",
        "A01",
        AisleStatus.CREATED,
        now,
        now,
        identification_mode=AisleIdentificationMode.INTERNAL_OCR,
    )
    use_case, job_repo, aisle_repo = _build_use_case(inventory=inv, aisle=aisle)

    first = use_case.execute(
        StartAisleProcessingCommand(
            inventory_id="inv1", aisle_id="a1", idempotency_key="req-key-1"
        )
    )

    mutated_aisle = aisle_repo.get_by_id("a1")
    assert mutated_aisle is not None
    mutated_aisle.identification_mode = AisleIdentificationMode.CODE_SCAN
    aisle_repo.save(mutated_aisle)

    replay = use_case.execute(
        StartAisleProcessingCommand(
            inventory_id="inv1", aisle_id="a1", idempotency_key="req-key-1"
        )
    )

    assert replay.job_id == first.job_id
    assert replay.identification_mode == "INTERNAL_OCR"
    assert replay.identification_mode_source == "AISLE"
    saved_job = job_repo.get_by_id(first.job_id)
    assert saved_job is not None
    assert saved_job.identification_mode == AisleIdentificationMode.INTERNAL_OCR


def test_distinct_idempotency_keys_create_distinct_jobs() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    inv = Inventory("inv1", "W", InventoryStatus.DRAFT, now, now)
    aisle = Aisle("a1", "inv1", "A01", AisleStatus.CREATED, now, now)
    use_case, job_repo, aisle_repo = _build_use_case(inventory=inv, aisle=aisle)

    first = use_case.execute(
        StartAisleProcessingCommand(
            inventory_id="inv1", aisle_id="a1", idempotency_key="req-key-1"
        )
    )
    # First attempt occupies the aisle; simulate it terminating so the second start is allowed.
    saved = job_repo.get_by_id(first.job_id)
    assert saved is not None
    from src.domain.jobs.entities import JobStatus

    saved.status = JobStatus.FAILED
    job_repo.save(saved)

    second = use_case.execute(
        StartAisleProcessingCommand(
            inventory_id="inv1", aisle_id="a1", idempotency_key="req-key-2"
        )
    )

    assert second.job_id != first.job_id
    assert len(job_repo.list_jobs_for_target("aisle", "a1", limit=100)) == 2


def test_no_idempotency_key_always_finds_no_replay_target() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    inv = Inventory("inv1", "W", InventoryStatus.DRAFT, now, now)
    aisle = Aisle("a1", "inv1", "A01", AisleStatus.CREATED, now, now)
    use_case, job_repo, _ = _build_use_case(inventory=inv, aisle=aisle)

    first = use_case.execute(StartAisleProcessingCommand(inventory_id="inv1", aisle_id="a1"))
    saved = job_repo.get_by_id(first.job_id)
    assert saved is not None
    assert saved.payload_json.get("idempotency_key") is None
