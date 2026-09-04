"""Exact historical profile version lookup — kind-scoped fallback."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.application.services.exact_extraction_profile_version import (
    ExactExtractionProfileVersionService,
    HistoricalProfileAttestation,
    ProfileVersionNotFoundError,
    ProfileVersionScopeMismatchError,
)
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.client_supplier.entities import ClientSupplier, ClientSupplierStatus
from src.domain.client_supplier.extraction_profile import (
    ExtractionProfileStatus,
    SupplierExtractionProfile,
    minimal_supplier_item_configuration,
    minimal_supplier_position_configuration,
)
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.domain.label_profiles.kinds import LabelKind
from src.infrastructure.repositories.memory_supplier_extraction_profile_repository import (
    MemorySupplierExtractionProfileRepository,
)


class _InvRepo:
    def __init__(self, inv: Inventory) -> None:
        self.inv = inv

    def get_by_id(self, inventory_id: str):
        return self.inv if self.inv.id == inventory_id else None


class _AisleRepo:
    def __init__(self, aisle: Aisle) -> None:
        self.aisle = aisle

    def get_by_id(self, aisle_id: str):
        return self.aisle if self.aisle.id == aisle_id else None


class _SupplierRepo:
    def __init__(self, supplier: ClientSupplier) -> None:
        self.supplier = supplier

    def get_by_id(self, supplier_id: str):
        return self.supplier if self.supplier.id == supplier_id else None


def _svc() -> tuple[ExactExtractionProfileVersionService, MemorySupplierExtractionProfileRepository]:
    now = datetime.now(timezone.utc)
    inv = Inventory(
        id="inv-1",
        name="T",
        status=InventoryStatus.DRAFT,
        created_at=now,
        updated_at=now,
        client_id="client-1",
    )
    aisle = Aisle(
        id="aisle-1",
        inventory_id="inv-1",
        code="A01",
        status=AisleStatus.CREATED,
        created_at=now,
        updated_at=now,
        client_supplier_id="sup-a",
    )
    supplier = ClientSupplier(
        id="sup-a",
        client_id="client-1",
        name="Sup A",
        status=ClientSupplierStatus.ACTIVE,
        created_at=now,
        updated_at=now,
    )
    profiles = MemorySupplierExtractionProfileRepository()
    item = SupplierExtractionProfile(
        id="item-id",
        client_id="client-1",
        supplier_id="sup-a",
        profile_key="ITEM",
        version=3,
        status=ExtractionProfileStatus.ACTIVE,
        configuration=minimal_supplier_item_configuration(expected_prefix="LPNA", exact_length=10),
        visual_notes=None,
        created_by=None,
        created_at=now,
        label_kind=LabelKind.ITEM,
    )
    position = SupplierExtractionProfile(
        id="pos-id",
        client_id="client-1",
        supplier_id="sup-a",
        profile_key="POSITION",
        version=3,
        status=ExtractionProfileStatus.ACTIVE,
        configuration=minimal_supplier_position_configuration(expected_prefix="A", exact_length=8),
        visual_notes=None,
        created_by=None,
        created_at=now,
        label_kind=LabelKind.POSITION,
    )
    profiles.save(item)
    profiles.save(position)
    svc = ExactExtractionProfileVersionService(
        inventory_repo=_InvRepo(inv),
        aisle_repo=_AisleRepo(aisle),
        client_supplier_repo=_SupplierRepo(supplier),
        extraction_profile_repo=profiles,
    )
    return svc, profiles


def test_version_fallback_loads_position_not_item_when_same_version() -> None:
    svc, _ = _svc()
    loaded = svc.load_for_aisle_capture(
        inventory_id="inv-1",
        aisle_id="aisle-1",
        attestation=HistoricalProfileAttestation(
            profile_id="missing-id",
            profile_version=3,
            client_supplier_id="sup-a",
            label_kind=LabelKind.POSITION,
        ),
    )
    assert loaded.id == "pos-id"
    assert loaded.label_kind is LabelKind.POSITION


def test_version_fallback_loads_item_when_kind_item() -> None:
    svc, _ = _svc()
    loaded = svc.load_for_aisle_capture(
        inventory_id="inv-1",
        aisle_id="aisle-1",
        attestation=HistoricalProfileAttestation(
            profile_id="missing-id",
            profile_version=3,
            client_supplier_id="sup-a",
            label_kind=LabelKind.ITEM,
        ),
    )
    assert loaded.id == "item-id"


def test_version_fallback_requires_label_kind() -> None:
    svc, _ = _svc()
    with pytest.raises(ProfileVersionNotFoundError):
        svc.load_for_aisle_capture(
            inventory_id="inv-1",
            aisle_id="aisle-1",
            attestation=HistoricalProfileAttestation(
                profile_id="missing-id",
                profile_version=3,
                client_supplier_id="sup-a",
                label_kind=None,
            ),
        )


def test_id_lookup_mismatched_kind_raises_scope() -> None:
    svc, _ = _svc()
    with pytest.raises(ProfileVersionScopeMismatchError):
        svc.load_for_aisle_capture(
            inventory_id="inv-1",
            aisle_id="aisle-1",
            attestation=HistoricalProfileAttestation(
                profile_id="item-id",
                profile_version=3,
                client_supplier_id="sup-a",
                label_kind=LabelKind.POSITION,
            ),
        )
