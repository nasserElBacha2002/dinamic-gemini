"""Unit tests for inventory offline recognition config bundle."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from src.application.use_cases.inventories.get_inventory_recognition_config import (
    GetInventoryRecognitionConfigCommand,
    GetInventoryRecognitionConfigUseCase,
    configuration_for_offline,
)
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.client_supplier.extraction_profile import (
    ExtractionProfileStatus,
    SupplierExtractionProfile,
    minimal_supplier_item_configuration,
    minimal_supplier_position_configuration,
)
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.domain.label_profiles.entities import ClientSupplierLabelProfile
from src.domain.label_profiles.kinds import LabelKind, LabelProfileSource


@dataclass
class _InvRepo:
    inv: Inventory

    def get_by_id(self, inventory_id: str):
        return self.inv if self.inv.id == inventory_id else None


@dataclass
class _AisleRepo:
    aisles: list[Aisle]

    def list_by_inventory(self, inventory_id: str):
        return [a for a in self.aisles if a.inventory_id == inventory_id]


@dataclass
class _ExtractionRepo:
    profiles: list[SupplierExtractionProfile]

    def list_by_supplier(self, client_id: str, supplier_id: str):
        return [
            p
            for p in self.profiles
            if p.client_id == client_id and p.supplier_id == supplier_id
        ]


@dataclass
class _LabelProfileRepo:
    rows: list[ClientSupplierLabelProfile]

    def get_by_supplier_and_kind(self, supplier_id: str, label_kind: LabelKind):
        for row in self.rows:
            if row.client_supplier_id == supplier_id and row.label_kind is label_kind:
                return row
        return None


def test_configuration_for_offline_strips_visual_and_ocr_sources() -> None:
    cfg = minimal_supplier_item_configuration(expected_prefix="LPNA", exact_length=10)
    profile = SupplierExtractionProfile(
        id="p1",
        client_id="c1",
        supplier_id="s1",
        profile_key="ITEM",
        version=1,
        status=ExtractionProfileStatus.ACTIVE,
        configuration=cfg,
        visual_notes="hint",
        created_by=None,
        created_at=datetime.now(timezone.utc),
        label_kind=LabelKind.ITEM,
    )
    slim = configuration_for_offline(profile)
    assert "deterministic" in slim
    assert "label_detection_rules" not in slim
    assert "internal_code_sources" not in slim
    assert slim["recognition_mode"] == "MINIMAL"


def test_bundle_includes_aisles_and_active_profiles_only() -> None:
    now = datetime.now(timezone.utc)
    inv = Inventory(
        id="inv-1",
        name="Test",
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
    item_cfg = minimal_supplier_item_configuration(expected_prefix="LPNA", exact_length=10)
    pos_cfg = minimal_supplier_position_configuration(expected_prefix="A", exact_length=8)
    profiles = [
        SupplierExtractionProfile(
            id="pi",
            client_id="client-1",
            supplier_id="sup-a",
            profile_key="ITEM",
            version=3,
            status=ExtractionProfileStatus.ACTIVE,
            configuration=item_cfg,
            visual_notes=None,
            created_by=None,
            created_at=now,
            label_kind=LabelKind.ITEM,
        ),
        SupplierExtractionProfile(
            id="pp",
            client_id="client-1",
            supplier_id="sup-a",
            profile_key="POSITION",
            version=2,
            status=ExtractionProfileStatus.ACTIVE,
            configuration=pos_cfg,
            visual_notes=None,
            created_by=None,
            created_at=now,
            label_kind=LabelKind.POSITION,
        ),
        SupplierExtractionProfile(
            id="old",
            client_id="client-1",
            supplier_id="sup-a",
            profile_key="ITEM",
            version=1,
            status=ExtractionProfileStatus.SUPERSEDED,
            configuration=item_cfg,
            visual_notes=None,
            created_by=None,
            created_at=now,
            label_kind=LabelKind.ITEM,
        ),
    ]
    label_rows = [
        ClientSupplierLabelProfile(
            id="lp-i",
            client_supplier_id="sup-a",
            label_kind=LabelKind.ITEM,
            source=LabelProfileSource.SUPPLIER,
            created_at=now,
            updated_at=now,
        ),
        ClientSupplierLabelProfile(
            id="lp-p",
            client_supplier_id="sup-a",
            label_kind=LabelKind.POSITION,
            source=LabelProfileSource.SUPPLIER,
            created_at=now,
            updated_at=now,
        ),
    ]
    uc = GetInventoryRecognitionConfigUseCase(
        inventory_repo=_InvRepo(inv),
        aisle_repo=_AisleRepo([aisle]),
        extraction_profile_repo=_ExtractionRepo(profiles),
        label_profile_repo=_LabelProfileRepo(label_rows),
    )
    bundle = uc.execute(GetInventoryRecognitionConfigCommand(inventory_id="inv-1"))
    assert bundle.bundle_schema_version == 1
    assert len(bundle.aisles) == 1
    assert bundle.aisles[0].effective_item_source == "SUPPLIER"
    assert len(bundle.profiles) == 2
    versions = {(p.label_kind, p.profile_version) for p in bundle.profiles}
    assert ("ITEM", 3) in versions
    assert ("POSITION", 2) in versions
    assert ("ITEM", 1) not in versions
    assert len(bundle.bundle_revision) == 64
    assert all(c in "0123456789abcdef" for c in bundle.bundle_revision)


def test_bundle_revision_stable_for_identical_content() -> None:
    from src.application.use_cases.inventories.get_inventory_recognition_config import (
        OfflineAisleConfig,
        OfflineProfileConfig,
        compute_offline_bundle_revision,
    )

    aisles = [
        OfflineAisleConfig(
            aisle_id="a1",
            aisle_code="A01",
            client_supplier_id="sup-a",
            item_profile_source_override=None,
            position_profile_source_override=None,
            effective_item_source="SUPPLIER",
            effective_position_source="SUPPLIER",
        )
    ]
    profiles = [
        OfflineProfileConfig(
            client_supplier_id="sup-a",
            label_kind="ITEM",
            source="SUPPLIER",
            profile_id="p1",
            profile_version=3,
            configuration_schema_version=2,
            recognition_mode="MINIMAL",
            semantic_type="LPN",
            configuration={
                "deterministic": {"expected_prefix": "LPNA", "exact_length": 10},
            },
        )
    ]
    r1 = compute_offline_bundle_revision(
        bundle_schema_version=1,
        inventory_id="inv-1",
        aisles=aisles,
        profiles=profiles,
    )
    r2 = compute_offline_bundle_revision(
        bundle_schema_version=1,
        inventory_id="inv-1",
        aisles=list(reversed(aisles)),
        profiles=list(reversed(profiles)),
    )
    assert r1 == r2


def test_bundle_revision_changes_on_mapping_and_config() -> None:
    from src.application.use_cases.inventories.get_inventory_recognition_config import (
        OfflineAisleConfig,
        OfflineProfileConfig,
        compute_offline_bundle_revision,
    )

    base_aisle = OfflineAisleConfig(
        aisle_id="a1",
        aisle_code="A01",
        client_supplier_id="sup-a",
        item_profile_source_override=None,
        position_profile_source_override=None,
        effective_item_source="SUPPLIER",
        effective_position_source="SUPPLIER",
    )
    base_profile = OfflineProfileConfig(
        client_supplier_id="sup-a",
        label_kind="ITEM",
        source="SUPPLIER",
        profile_id="p1",
        profile_version=3,
        configuration_schema_version=2,
        recognition_mode="MINIMAL",
        semantic_type="LPN",
        configuration={"deterministic": {"expected_prefix": "LPNA", "exact_length": 10}},
    )
    base = compute_offline_bundle_revision(
        bundle_schema_version=1,
        inventory_id="inv-1",
        aisles=[base_aisle],
        profiles=[base_profile],
    )
    supplier_changed = compute_offline_bundle_revision(
        bundle_schema_version=1,
        inventory_id="inv-1",
        aisles=[
            OfflineAisleConfig(
                **{
                    **base_aisle.__dict__,
                    "client_supplier_id": "sup-b",
                }
            )
        ],
        profiles=[base_profile],
    )
    assert supplier_changed != base

    override_changed = compute_offline_bundle_revision(
        bundle_schema_version=1,
        inventory_id="inv-1",
        aisles=[
            OfflineAisleConfig(
                **{
                    **base_aisle.__dict__,
                    "item_profile_source_override": "DINAMIC",
                }
            )
        ],
        profiles=[base_profile],
    )
    assert override_changed != base

    effective_changed = compute_offline_bundle_revision(
        bundle_schema_version=1,
        inventory_id="inv-1",
        aisles=[
            OfflineAisleConfig(
                **{
                    **base_aisle.__dict__,
                    "effective_item_source": "DINAMIC",
                }
            )
        ],
        profiles=[base_profile],
    )
    assert effective_changed != base

    version_changed = compute_offline_bundle_revision(
        bundle_schema_version=1,
        inventory_id="inv-1",
        aisles=[base_aisle],
        profiles=[
            OfflineProfileConfig(
                **{**base_profile.__dict__, "profile_version": 4},
            )
        ],
    )
    assert version_changed != base

    config_changed = compute_offline_bundle_revision(
        bundle_schema_version=1,
        inventory_id="inv-1",
        aisles=[base_aisle],
        profiles=[
            OfflineProfileConfig(
                **{
                    **base_profile.__dict__,
                    "configuration": {
                        "deterministic": {"expected_prefix": "XXXX", "exact_length": 10}
                    },
                },
            )
        ],
    )
    assert config_changed != base
