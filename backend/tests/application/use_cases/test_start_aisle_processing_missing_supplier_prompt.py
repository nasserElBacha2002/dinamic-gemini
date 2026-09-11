"""AUTO label-code start must not hard-fail on missing supplier Vision prompt."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from src.application.services.inventory_status_reconciler import InventoryStatusReconciler
from src.application.use_cases.aisles.start_aisle_processing import (
    StartAisleProcessingCommand,
    StartAisleProcessingUseCase,
)
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.client_supplier.entities import ClientSupplier, ClientSupplierStatus
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.infrastructure.repositories.memory_client_supplier_repository import (
    MemoryClientSupplierRepository,
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

_NOW = datetime(2026, 9, 10, 12, 0, 0, tzinfo=timezone.utc)


def _settings(**overrides: object) -> SimpleNamespace:
    base = {
        "aisle_identification_pipeline_enabled": True,
        "code_scan_processing_enabled": True,
        "internal_ocr_processing_enabled": False,
        "external_fallback_per_image_enabled": True,
        "code_scan_vision_fallback_enabled": True,
        "external_fallback_provider": "gemini",
        "external_fallback_model": "gemini-2.0-flash",
        "external_fallback_mode": "GLOBAL_BATCH",
        "multi_provider_fallback_enabled": False,
        "external_fallback_timeout_seconds": 60,
        "external_fallback_max_attempts": 1,
        "max_external_fallback_concurrency": 1,
        "external_fallback_max_image_dimension": 2048,
        "code_scan_quantity_max": 99_999_999,
        "internal_ocr_quantity_max": 99_999_999,
        "external_fallback_circuit_breaker_threshold": 5,
        "external_fallback_circuit_breaker_cooldown_seconds": 60,
        "external_fallback_ambiguous_internal_code_enabled": False,
        "client_extraction_profiles_enabled": False,
        "profile_aware_validation_enabled": False,
        "reference_template_annotations_enabled": False,
        "internal_ocr_ean_first_client_ids": "",
        "internal_ocr_prefer_ean_as_internal_code": False,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _use_case(
    *,
    job_repo: StubJobRepo,
    supplier_repo: MemoryClientSupplierRepository,
    prompt_repo: MemorySupplierPromptConfigRepository,
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
        supplier_prompt_config_repo=prompt_repo,
    )


def test_auto_without_supplier_prompt_starts_code_scan_without_vision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Label-code AUTO path must start even when Vision prompt is missing."""
    monkeypatch.setattr(
        "src.application.use_cases.aisles.start_aisle_processing.load_settings",
        lambda: _settings(),
    )
    monkeypatch.setattr(
        "src.pipeline.providers.registry.resolve_llm_executor",
        lambda *_a, **_k: object(),
    )
    job_repo = StubJobRepo()
    uc = _use_case(
        job_repo=job_repo,
        supplier_repo=MemoryClientSupplierRepository(),
        prompt_repo=MemorySupplierPromptConfigRepository(),  # empty → no active prompt
    )
    result = uc.execute(
        StartAisleProcessingCommand(
            inventory_id="inv1",
            aisle_id="a1",
            principal=platform_principal(),
            requested_processing_mode="AUTO",
        )
    )
    job = job_repo.get_by_id(result.job_id)
    assert job is not None
    ident = (job.engine_params_json or {}).get("identification_execution") or {}
    fallback = ident.get("external_fallback") or {}
    assert fallback.get("fallback_enabled") is False
    assert ident.get("supplier_prompt") in (None, {})


def test_vision_only_without_supplier_prompt_still_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "src.application.use_cases.aisles.start_aisle_processing.load_settings",
        lambda: _settings(),
    )
    monkeypatch.setattr(
        "src.pipeline.providers.registry.resolve_llm_executor",
        lambda *_a, **_k: object(),
    )
    uc = _use_case(
        job_repo=StubJobRepo(),
        supplier_repo=MemoryClientSupplierRepository(),
        prompt_repo=MemorySupplierPromptConfigRepository(),
    )
    with pytest.raises(ValueError, match="SUPPLIER_PROMPT_REQUIRED"):
        uc.execute(
            StartAisleProcessingCommand(
                inventory_id="inv1",
                aisle_id="a1",
                principal=platform_principal(),
                requested_processing_mode="VISION_ONLY",
            )
        )
