"""StartAisleProcessingUseCase — immutable label_profiles snapshot (Phase 1 corrections)."""

from __future__ import annotations

from datetime import datetime, timezone

from src.application.services.inventory_status_reconciler import InventoryStatusReconciler
from src.application.use_cases.aisles.start_aisle_processing import (
    StartAisleProcessingCommand,
    StartAisleProcessingUseCase,
)
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.client_supplier.entities import ClientSupplier, ClientSupplierStatus
from src.domain.client_supplier.extraction_profile import (
    ExtractionProfileStatus,
    SupplierExtractionProfile,
    default_extraction_configuration,
)
from src.domain.client_supplier.prompt_config import SupplierPromptConfig
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.domain.jobs.entities import Job, JobStatus
from src.domain.label_profiles.entities import ClientSupplierLabelProfile
from src.domain.label_profiles.kinds import LabelKind, LabelProfileSource
from src.infrastructure.repositories.memory_client_supplier_label_profile_repository import (
    MemoryClientSupplierLabelProfileRepository,
)
from src.infrastructure.repositories.memory_client_supplier_repository import (
    MemoryClientSupplierRepository,
)
from src.infrastructure.repositories.memory_supplier_extraction_profile_repository import (
    MemorySupplierExtractionProfileRepository,
)
from src.infrastructure.repositories.memory_supplier_prompt_config_repository import (
    MemorySupplierPromptConfigRepository,
)
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
from tests.support.access_principal_helpers import platform_principal, policy_for

_NOW = datetime(2026, 8, 31, 12, 0, 0, tzinfo=timezone.utc)


def _build_use_case(
    *,
    job_repo: StubJobRepo,
    extraction_repo: MemorySupplierExtractionProfileRepository,
    prompt_repo: MemorySupplierPromptConfigRepository,
    label_repo: MemoryClientSupplierLabelProfileRepository,
    supplier_repo: MemoryClientSupplierRepository,
) -> StartAisleProcessingUseCase:
    inv_repo = StubInventoryRepo(
        [
            Inventory(
                id="inv1",
                name="inv",
                status=InventoryStatus.DRAFT,
                created_at=_NOW,
                updated_at=_NOW,
                client_id="c1",
            )
        ]
    )
    aisle_repo = StubAisleRepo()
    aisle_repo.save(
        Aisle(
            id="a1",
            inventory_id="inv1",
            code="A1",
            status=AisleStatus.CREATED,
            created_at=_NOW,
            updated_at=_NOW,
            client_supplier_id="sup1",
        )
    )
    clock = FixedClock(_NOW)
    reconciler = InventoryStatusReconciler(inv_repo, aisle_repo, clock)
    return StartAisleProcessingUseCase(
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        asset_repo=_stub_asset_repo_with_one_photo(),
        job_repo=job_repo,
        launch_service=make_launch_service(
            aisle_repo=aisle_repo,
            job_repo=job_repo,
            worker_launch_service=StubWorkerLaunchService(),
            clock=clock,
            reconciler=reconciler,
        ),
        stale_reconciler=make_stale_reconciler(job_repo, clock),
        access_policy=policy_for(inv_repo, aisle_repo),
        client_supplier_repo=supplier_repo,
        label_profile_repo=label_repo,
        extraction_profile_repo=extraction_repo,
        supplier_prompt_config_repo=prompt_repo,
    )


def _item_extraction_version(job: Job) -> int | None:
    raw = job.engine_params_json or {}
    ident = raw.get("identification_execution") or {}
    profiles = ident.get("label_profiles") or {}
    item = profiles.get("item") or {}
    version = item.get("extraction_profile_version")
    return int(version) if version is not None else None


def test_job_a_keeps_v1_after_supplier_config_v2_activation() -> None:
    job_repo = StubJobRepo()
    extraction_repo = MemorySupplierExtractionProfileRepository()
    prompt_repo = MemorySupplierPromptConfigRepository()
    label_repo = MemoryClientSupplierLabelProfileRepository()
    supplier_repo = MemoryClientSupplierRepository()
    supplier_repo.save(
        ClientSupplier(
            id="sup1",
            client_id="c1",
            name="Sup",
            status=ClientSupplierStatus.ACTIVE,
            created_at=_NOW,
            updated_at=_NOW,
        )
    )
    label_repo.upsert(
        ClientSupplierLabelProfile(
            id="lp-item",
            client_supplier_id="sup1",
            label_kind=LabelKind.ITEM,
            source=LabelProfileSource.SUPPLIER,
            created_at=_NOW,
            updated_at=_NOW,
        )
    )
    extraction_repo.save(
        SupplierExtractionProfile(
            id="ep-v1",
            client_id="c1",
            supplier_id="sup1",
            profile_key="default",
            version=1,
            status=ExtractionProfileStatus.ACTIVE,
            configuration=default_extraction_configuration(),
            visual_notes=None,
            created_by=None,
            created_at=_NOW,
            updated_at=_NOW,
            label_kind=LabelKind.ITEM,
        )
    )
    prompt_repo.create(
        SupplierPromptConfig(
            id="prompt-v1",
            client_supplier_id="sup1",
            provider_name=None,
            model_name=None,
            instructions_text="v1",
            version=1,
            is_active=True,
            created_at=_NOW,
            updated_at=_NOW,
            label_kind=LabelKind.ITEM,
        )
    )

    uc = _build_use_case(
        job_repo=job_repo,
        extraction_repo=extraction_repo,
        prompt_repo=prompt_repo,
        label_repo=label_repo,
        supplier_repo=supplier_repo,
    )
    job_a_id = uc.execute(
        StartAisleProcessingCommand(
            inventory_id="inv1", aisle_id="a1", principal=platform_principal()
        )
    ).job_id
    job_a = job_repo.get_by_id(job_a_id)
    assert job_a is not None
    v1_snapshot = _item_extraction_version(job_a)
    assert v1_snapshot == 1
    job_a.status = JobStatus.SUCCEEDED
    job_repo.save(job_a)

    extraction_repo.save(
        SupplierExtractionProfile(
            id="ep-v2",
            client_id="c1",
            supplier_id="sup1",
            profile_key="default",
            version=2,
            status=ExtractionProfileStatus.DRAFT,
            configuration=default_extraction_configuration(),
            visual_notes=None,
            created_by=None,
            created_at=_NOW,
            updated_at=_NOW,
            label_kind=LabelKind.ITEM,
        )
    )
    extraction_repo.activate_version(
        client_id="c1", supplier_id="sup1", profile_id="ep-v2", activated_by="tester"
    )

    reloaded = job_repo.get_by_id(job_a_id)
    assert reloaded is not None
    assert _item_extraction_version(reloaded) == 1

    job_b_id = uc.execute(
        StartAisleProcessingCommand(
            inventory_id="inv1", aisle_id="a1", principal=platform_principal()
        )
    ).job_id
    job_b = job_repo.get_by_id(job_b_id)
    assert job_b is not None
    assert job_b_id != job_a_id
    assert _item_extraction_version(job_b) == 2


def test_legacy_job_without_label_profiles_still_loads() -> None:
    job_repo = StubJobRepo()
    legacy = Job(
        id="legacy-job",
        target_type="aisle",
        target_id="a1",
        job_type="process_aisle",
        status=JobStatus.SUCCEEDED,
        payload_json={},
        created_at=_NOW,
        updated_at=_NOW,
        engine_params_json={
            "identification_execution": {
                "supplier_extraction_profile": {"version": 1},
                "supplier_prompt": {"version": 1},
            }
        },
    )
    job_repo.save(legacy)
    loaded = job_repo.get_by_id("legacy-job")
    assert loaded is not None
    ident = (loaded.engine_params_json or {}).get("identification_execution") or {}
    assert ident.get("label_profiles") is None
