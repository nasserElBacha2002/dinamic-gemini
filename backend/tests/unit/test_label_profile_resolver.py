"""Unit tests for LabelProfileResolver (Phase 1)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.application.errors import ClientSupplierClientMismatchError
from src.application.services.label_profile_resolver import (
    LabelProfileResolutionContext,
    LabelProfileResolver,
)
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.client_supplier.entities import ClientSupplier, ClientSupplierStatus
from src.domain.client_supplier.extraction_profile import (
    ExtractionProfileConfiguration,
    ExtractionProfileStatus,
    SupplierExtractionProfile,
)
from src.domain.client_supplier.prompt_config import SupplierPromptConfig
from src.domain.label_profiles.entities import ClientSupplierLabelProfile
from src.domain.label_profiles.errors import SupplierLabelProfileNotConfiguredError
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

_NOW = datetime(2026, 8, 31, 12, 0, 0, tzinfo=timezone.utc)


def _aisle(**overrides) -> Aisle:
    base = dict(
        id="aisle-1",
        inventory_id="inv-1",
        code="A1",
        status=AisleStatus.CREATED,
        created_at=_NOW,
        updated_at=_NOW,
        client_supplier_id="sup-1",
    )
    base.update(overrides)
    return Aisle(**base)


def _supplier(client_id: str = "client-1", supplier_id: str = "sup-1") -> ClientSupplier:
    return ClientSupplier(
        id=supplier_id,
        client_id=client_id,
        name="Supplier",
        status=ClientSupplierStatus.ACTIVE,
        created_at=_NOW,
        updated_at=_NOW,
    )


def _active_extraction(
    *,
    client_id: str = "client-1",
    supplier_id: str = "sup-1",
    profile_id: str = "ext-1",
    version: int = 1,
    label_kind: LabelKind | None = LabelKind.ITEM,
) -> SupplierExtractionProfile:
    return SupplierExtractionProfile(
        id=profile_id,
        client_id=client_id,
        supplier_id=supplier_id,
        profile_key="default",
        version=version,
        status=ExtractionProfileStatus.ACTIVE,
        configuration=ExtractionProfileConfiguration(),
        visual_notes=None,
        created_by=None,
        created_at=_NOW,
        label_kind=label_kind,
    )


def _active_prompt(
    *,
    supplier_id: str = "sup-1",
    prompt_id: str = "prompt-1",
    version: int = 1,
    label_kind: LabelKind | None = LabelKind.ITEM,
) -> SupplierPromptConfig:
    return SupplierPromptConfig(
        id=prompt_id,
        client_supplier_id=supplier_id,
        provider_name=None,
        model_name=None,
        instructions_text="Read SKU and quantity",
        version=version,
        is_active=True,
        created_at=_NOW,
        updated_at=_NOW,
        label_kind=label_kind,
    )


@pytest.fixture
def resolver_bundle():
    label_profiles = MemoryClientSupplierLabelProfileRepository()
    suppliers = MemoryClientSupplierRepository()
    extraction = MemorySupplierExtractionProfileRepository()
    prompts = MemorySupplierPromptConfigRepository()
    suppliers.save(_supplier())
    resolver = LabelProfileResolver(
        label_profile_repo=label_profiles,
        client_supplier_repo=suppliers,
        extraction_profile_repo=extraction,
        supplier_prompt_config_repo=prompts,
    )
    return resolver, label_profiles, suppliers, extraction, prompts


def test_no_supplier_defaults_dinamic(resolver_bundle) -> None:
    resolver, *_ = resolver_bundle
    resolved = resolver.resolve(
        LabelProfileResolutionContext(client_id="client-1", client_supplier_id=None)
    )
    assert resolved.item.source is LabelProfileSource.DINAMIC
    assert resolved.position.source is LabelProfileSource.DINAMIC


def test_supplier_without_config_defaults_dinamic(resolver_bundle) -> None:
    resolver, *_ = resolver_bundle
    resolved = resolver.resolve(
        LabelProfileResolutionContext(
            client_id="client-1", client_supplier_id="sup-1", aisle=_aisle()
        )
    )
    assert resolved.item.source is LabelProfileSource.DINAMIC
    assert resolved.position.source is LabelProfileSource.DINAMIC


def test_supplier_item_custom_position_dinamic(resolver_bundle) -> None:
    resolver, label_profiles, _, extraction, prompts = resolver_bundle
    label_profiles.upsert(
        ClientSupplierLabelProfile(
            id="cfg-item",
            client_supplier_id="sup-1",
            label_kind=LabelKind.ITEM,
            source=LabelProfileSource.SUPPLIER,
            created_at=_NOW,
            updated_at=_NOW,
        )
    )
    extraction.save(_active_extraction(label_kind=LabelKind.ITEM))
    prompts.create(_active_prompt(label_kind=LabelKind.ITEM))
    resolved = resolver.resolve(
        LabelProfileResolutionContext(
            client_id="client-1", client_supplier_id="sup-1", aisle=_aisle()
        )
    )
    assert resolved.item.source is LabelProfileSource.SUPPLIER
    assert resolved.position.source is LabelProfileSource.DINAMIC


def test_supplier_position_custom_item_dinamic(resolver_bundle) -> None:
    resolver, label_profiles, _, extraction, prompts = resolver_bundle
    label_profiles.upsert(
        ClientSupplierLabelProfile(
            id="cfg-pos",
            client_supplier_id="sup-1",
            label_kind=LabelKind.POSITION,
            source=LabelProfileSource.SUPPLIER,
            created_at=_NOW,
            updated_at=_NOW,
        )
    )
    extraction.save(_active_extraction(profile_id="ext-pos", label_kind=LabelKind.POSITION))
    prompts.create(_active_prompt(prompt_id="prompt-pos", version=2, label_kind=LabelKind.POSITION))
    resolved = resolver.resolve(
        LabelProfileResolutionContext(
            client_id="client-1", client_supplier_id="sup-1", aisle=_aisle()
        )
    )
    assert resolved.item.source is LabelProfileSource.DINAMIC
    assert resolved.position.source is LabelProfileSource.SUPPLIER


def test_supplier_both_supplier(resolver_bundle) -> None:
    resolver, label_profiles, _, extraction, prompts = resolver_bundle
    for kind, cfg_id in ((LabelKind.ITEM, "cfg-i"), (LabelKind.POSITION, "cfg-p")):
        label_profiles.upsert(
            ClientSupplierLabelProfile(
                id=cfg_id,
                client_supplier_id="sup-1",
                label_kind=kind,
                source=LabelProfileSource.SUPPLIER,
                created_at=_NOW,
                updated_at=_NOW,
            )
        )
    extraction.save(_active_extraction(label_kind=LabelKind.ITEM))
    extraction.save(
        _active_extraction(profile_id="ext-pos", label_kind=LabelKind.POSITION, version=1)
    )
    resolved = resolver.resolve(
        LabelProfileResolutionContext(
            client_id="client-1", client_supplier_id="sup-1", aisle=_aisle()
        )
    )
    assert resolved.item.source is LabelProfileSource.SUPPLIER
    assert resolved.position.source is LabelProfileSource.SUPPLIER


def test_aisle_item_override_dinamic_beats_supplier_item(resolver_bundle) -> None:
    resolver, label_profiles, _, extraction, prompts = resolver_bundle
    label_profiles.upsert(
        ClientSupplierLabelProfile(
            id="cfg-item",
            client_supplier_id="sup-1",
            label_kind=LabelKind.ITEM,
            source=LabelProfileSource.SUPPLIER,
            created_at=_NOW,
            updated_at=_NOW,
        )
    )
    extraction.save(_active_extraction())
    prompts.create(_active_prompt())
    aisle = _aisle(item_profile_source_override=LabelProfileSource.DINAMIC)
    resolved = resolver.resolve(
        LabelProfileResolutionContext(
            client_id="client-1", client_supplier_id="sup-1", aisle=aisle
        )
    )
    assert resolved.item.source is LabelProfileSource.DINAMIC
    assert resolved.item.resolution_source == "AISLE_OVERRIDE"


def test_aisle_position_override_dinamic(resolver_bundle) -> None:
    resolver, label_profiles, _, extraction, prompts = resolver_bundle
    label_profiles.upsert(
        ClientSupplierLabelProfile(
            id="cfg-pos",
            client_supplier_id="sup-1",
            label_kind=LabelKind.POSITION,
            source=LabelProfileSource.SUPPLIER,
            created_at=_NOW,
            updated_at=_NOW,
        )
    )
    extraction.save(_active_extraction(profile_id="ext-pos", label_kind=LabelKind.POSITION))
    prompts.create(_active_prompt(prompt_id="prompt-pos", version=2, label_kind=LabelKind.POSITION))
    aisle = _aisle(position_profile_source_override=LabelProfileSource.DINAMIC)
    resolved = resolver.resolve(
        LabelProfileResolutionContext(
            client_id="client-1", client_supplier_id="sup-1", aisle=aisle
        )
    )
    assert resolved.position.source is LabelProfileSource.DINAMIC


def test_forced_supplier_without_backing_raises(resolver_bundle) -> None:
    resolver, label_profiles, *_ = resolver_bundle
    label_profiles.upsert(
        ClientSupplierLabelProfile(
            id="cfg-item",
            client_supplier_id="sup-1",
            label_kind=LabelKind.ITEM,
            source=LabelProfileSource.SUPPLIER,
            created_at=_NOW,
            updated_at=_NOW,
        )
    )
    aisle = _aisle()
    with pytest.raises(SupplierLabelProfileNotConfiguredError):
        resolver.resolve(
            LabelProfileResolutionContext(
                client_id="client-1", client_supplier_id="sup-1", aisle=aisle
            )
        )


def test_wrong_client_rejected(resolver_bundle) -> None:
    resolver, *_ = resolver_bundle
    with pytest.raises(ClientSupplierClientMismatchError):
        resolver.resolve(
            LabelProfileResolutionContext(
                client_id="other-client", client_supplier_id="sup-1", aisle=_aisle()
            )
        )


def test_job_snapshot_immutable_after_supplier_config_change(resolver_bundle) -> None:
    resolver, label_profiles, _, extraction, prompts = resolver_bundle
    label_profiles.upsert(
        ClientSupplierLabelProfile(
            id="cfg-item",
            client_supplier_id="sup-1",
            label_kind=LabelKind.ITEM,
            source=LabelProfileSource.SUPPLIER,
            created_at=_NOW,
            updated_at=_NOW,
        )
    )
    extraction.save(_active_extraction(profile_id="ext-v1", version=1))
    ctx = LabelProfileResolutionContext(
        client_id="client-1", client_supplier_id="sup-1", aisle=_aisle()
    )
    job_a_snapshot = resolver.resolve(ctx).to_snapshot_dict()

    extraction.save(_active_extraction(profile_id="ext-v2", version=2))
    job_b_snapshot = resolver.resolve(ctx).to_snapshot_dict()

    assert job_a_snapshot["item"]["extraction_profile_version"] == 1
    assert job_b_snapshot["item"]["extraction_profile_version"] == 2
    assert job_a_snapshot != job_b_snapshot
