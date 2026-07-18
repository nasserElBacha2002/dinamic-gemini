"""Start-aisle identification mode snapshot tests (Phase 1)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.application.services.aisle_job_launch_service import AisleJobLaunchService
from src.application.services.inventory_status_reconciler import InventoryStatusReconciler
from src.application.use_cases.aisles.start_aisle_processing import (
    StartAisleProcessingCommand,
    StartAisleProcessingUseCase,
)
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.aisle_identification.modes import (
    AisleIdentificationExecutionStrategy,
    AisleIdentificationMode,
    AisleIdentificationModeSource,
    historical_job_identification_mode,
)
from src.domain.assets.entities import SourceAsset, SourceAssetType
from src.domain.client.entities import Client, ClientStatus
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.domain.jobs.entities import Job, JobStatus
from tests.application.use_cases.test_aisle_processing import (
    FixedClock,
    StubAisleRepo,
    StubAssetRepo,
    StubInventoryRepo,
    StubJobRepo,
    StubWorkerLaunchService,
    make_stale_reconciler,
)


class StubClientRepo:
    def __init__(self, clients: list[Client] | None = None) -> None:
        self._store = {c.id: c for c in (clients or [])}

    def save(self, client: Client) -> None:
        self._store[client.id] = client

    def get_by_id(self, client_id: str) -> Client | None:
        return self._store.get(client_id)

    def list_all(self):
        return list(self._store.values())


def _photo(aisle_id: str = "a1") -> SourceAsset:
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    return SourceAsset(
        id="sa1",
        aisle_id=aisle_id,
        type=SourceAssetType.PHOTO,
        original_filename="seed.jpg",
        storage_path="uploads/seed",
        mime_type="image/jpeg",
        uploaded_at=now,
    )


def _build_use_case(
    *,
    inventory: Inventory,
    aisle: Aisle,
    client: Client | None = None,
    pipeline_enabled: bool = True,
):
    now = aisle.created_at
    inv_repo = StubInventoryRepo([inventory])
    aisle_repo = StubAisleRepo()
    aisle_repo.save(aisle)
    asset_repo = StubAssetRepo()
    asset_repo.save(_photo(aisle.id))
    job_repo = StubJobRepo()
    queue = StubWorkerLaunchService()
    clock = FixedClock(now)
    reconciler = InventoryStatusReconciler(inv_repo, aisle_repo, clock)
    client_repo = StubClientRepo([client] if client else [])
    use_case = StartAisleProcessingUseCase(
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        asset_repo=asset_repo,
        job_repo=job_repo,
        launch_service=AisleJobLaunchService(
            aisle_repo=aisle_repo,
            job_repo=job_repo,
            worker_launch_service=queue,
            clock=clock,
            status_reconciler=reconciler,
        ),
        stale_reconciler=make_stale_reconciler(job_repo, clock),
        client_repo=client_repo,
    )
    return use_case, job_repo, aisle_repo


def test_create_job_with_request_code_scan(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AISLE_IDENTIFICATION_PIPELINE_ENABLED", "true")
    from src.config import reload_settings

    reload_settings()
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    inv = Inventory("inv1", "W", InventoryStatus.DRAFT, now, now)
    aisle = Aisle("a1", "inv1", "A01", AisleStatus.CREATED, now, now)
    uc, job_repo, _ = _build_use_case(inventory=inv, aisle=aisle)
    result = uc.execute(
        StartAisleProcessingCommand(
            inventory_id="inv1",
            aisle_id="a1",
            requested_identification_mode="CODE_SCAN",
        )
    )
    assert result.identification_mode == "CODE_SCAN"
    assert result.identification_mode_source == "REQUEST"
    assert result.execution_strategy == "LEGACY_LLM_TEMPORARY"
    job = job_repo.get_by_id(result.job_id)
    assert job is not None
    assert job.identification_mode == AisleIdentificationMode.CODE_SCAN
    assert job.execution_strategy == AisleIdentificationExecutionStrategy.LEGACY_LLM_TEMPORARY


def test_create_job_inherits_aisle_then_snapshot_immutable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AISLE_IDENTIFICATION_PIPELINE_ENABLED", "true")
    from src.config import reload_settings

    reload_settings()
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
    uc, job_repo, aisle_repo = _build_use_case(inventory=inv, aisle=aisle)
    result = uc.execute(StartAisleProcessingCommand(inventory_id="inv1", aisle_id="a1"))
    assert result.identification_mode == "INTERNAL_OCR"
    assert result.identification_mode_source == "AISLE"
    job = job_repo.get_by_id(result.job_id)
    assert job is not None
    aisle2 = aisle_repo.get_by_id("a1")
    assert aisle2 is not None
    aisle2.identification_mode = AisleIdentificationMode.CODE_SCAN
    aisle_repo.save(aisle2)
    reloaded = job_repo.get_by_id(result.job_id)
    assert reloaded is not None
    assert reloaded.identification_mode == AisleIdentificationMode.INTERNAL_OCR
    assert reloaded.identification_mode_source == AisleIdentificationModeSource.AISLE


def test_create_job_inherits_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AISLE_IDENTIFICATION_PIPELINE_ENABLED", "false")
    from src.config import reload_settings

    reload_settings()
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    client = Client(
        "c1",
        "Acme",
        ClientStatus.ACTIVE,
        now,
        now,
        default_identification_mode=AisleIdentificationMode.CODE_SCAN,
    )
    inv = Inventory("inv1", "W", InventoryStatus.DRAFT, now, now, client_id="c1")
    aisle = Aisle("a1", "inv1", "A01", AisleStatus.CREATED, now, now)
    uc, job_repo, _ = _build_use_case(inventory=inv, aisle=aisle, client=client)
    result = uc.execute(StartAisleProcessingCommand(inventory_id="inv1", aisle_id="a1"))
    assert result.identification_mode == "CODE_SCAN"
    assert result.identification_mode_source == "CLIENT"
    # Flag off → still legacy execution label (not TEMPORARY)
    assert result.execution_strategy == "LEGACY_LLM"
    job = job_repo.get_by_id(result.job_id)
    assert job is not None
    assert job.execution_strategy == AisleIdentificationExecutionStrategy.LEGACY_LLM


def test_historical_job_null_fields_coerce() -> None:
    now = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
    job = Job(
        id="legacy",
        target_type="aisle",
        target_id="a1",
        job_type="process_aisle",
        status=JobStatus.SUCCEEDED,
        payload_json={},
        created_at=now,
        updated_at=now,
    )
    assert job.identification_mode == AisleIdentificationMode.LEGACY_LLM
    assert historical_job_identification_mode(None) == AisleIdentificationMode.LEGACY_LLM
