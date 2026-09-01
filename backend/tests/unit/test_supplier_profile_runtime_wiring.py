"""Supplier profile runtime wiring — CODE_SCAN integration regressions."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from src.application.ports.code_scanner import CodeScanDetectionCandidate
from src.application.services.image_processing.code_detection_consolidator import (
    CodeDetectionConsolidator,
)
from src.application.services.image_processing.code_scan_processing_strategy import (
    CodeScanConfig,
    CodeScanProcessingStrategy,
)
from src.application.services.image_processing.encoded_label_payload_parser import (
    EncodedLabelPayloadParser,
)
from src.application.services.label_validation import (
    LabelValidationContext,
    LabelValidationService,
)
from src.application.services.supplier_label_profile_wiring import (
    detect_supplier_wiring_mismatch,
    upsert_effective_label_source,
)
from src.application.use_cases.suppliers.manage_supplier_extraction_profiles import (
    ActivateSupplierExtractionProfileVersionCommand,
    ActivateSupplierExtractionProfileVersionUseCase,
    CreateSupplierExtractionProfileVersionCommand,
    CreateSupplierExtractionProfileVersionUseCase,
)
from src.domain.aisle_identification.modes import (
    AisleIdentificationExecutionStrategy,
    AisleIdentificationMode,
)
from src.domain.assets.entities import SourceAsset, SourceAssetType
from src.domain.client_supplier.extraction_profile import (
    CONFIGURATION_SCHEMA_VERSION_V2,
    DeterministicBarcodeRules,
    ExtractionProfileConfiguration,
    ExtractionProfileStatus,
    FieldMappingRule,
    FieldMappingSource,
    PayloadStructure,
    QuantityExtractionRules,
    SupplierExtractionProfile,
    minimal_supplier_item_configuration,
)
from src.domain.code_scans.entities import CodeType
from src.domain.image_processing.contracts import ImageProcessingContext, ImageResultStatus
from src.domain.label_profiles.entities import ResolvedLabelProfile, ResolvedLabelProfiles
from src.domain.label_profiles.kinds import LabelKind, LabelProfileSource
from src.infrastructure.repositories.memory_client_supplier_label_profile_repository import (
    MemoryClientSupplierLabelProfileRepository,
)
from src.infrastructure.repositories.memory_supplier_extraction_profile_repository import (
    MemorySupplierExtractionProfileRepository,
)
from src.infrastructure.repositories.memory_image_position_label_detection_repository import (
    MemoryImagePositionLabelDetectionRepository,
)
from src.domain.product_labels.format import (
    build_product_label_payload,
    generate_product_label_id,
)

_NOW = datetime(2026, 8, 31, 12, 0, 0, tzinfo=timezone.utc)


class _FixedClock:
    def now(self):
        return _NOW


class _Reader:
    def read_image_bytes(self, asset: SourceAsset) -> bytes:
        return b"fake-image"


class _Scanner:
    def __init__(self, value: str) -> None:
        self._value = value

    @property
    def engine_name(self) -> str:
        return "test"

    def scan_asset(self, asset, content=None):
        return [
            CodeScanDetectionCandidate(
                code_type=CodeType.BARCODE,
                code_value=self._value,
                confidence=1.0,
                bounding_box_json=None,
                metadata_json={"pyzbar_type": "QRCODE"},
            )
        ]


def _position_segmented_config() -> ExtractionProfileConfiguration:
    return ExtractionProfileConfiguration(
        configuration_schema_version=CONFIGURATION_SCHEMA_VERSION_V2,
        required_fields=("position_id",),
        accepted_barcode_formats=("QR",),
        quantity_rules=QuantityExtractionRules(required=False),
        deterministic=DeterministicBarcodeRules(
            payload_structure=PayloadStructure.SEGMENTED,
            delimiter="|",
            expected_segment_count=4,
            field_mappings=(
                FieldMappingRule("position_id", FieldMappingSource.SEGMENT, 0),
                FieldMappingRule("pallet", FieldMappingSource.SEGMENT, 1),
                FieldMappingRule("side", FieldMappingSource.SEGMENT, 2),
                FieldMappingRule("level", FieldMappingSource.SEGMENT, 3),
            ),
        ),
    )


def _item_segmented_config() -> ExtractionProfileConfiguration:
    return ExtractionProfileConfiguration(
        configuration_schema_version=CONFIGURATION_SCHEMA_VERSION_V2,
        required_fields=("label_id", "sku", "quantity"),
        accepted_barcode_formats=("QR", "CODE128"),
        quantity_rules=QuantityExtractionRules(required=True, minimum=1),
        deterministic=DeterministicBarcodeRules(
            payload_structure=PayloadStructure.SEGMENTED,
            delimiter="|",
            expected_segment_count=3,
            field_mappings=(
                FieldMappingRule("label_id", FieldMappingSource.SEGMENT, 0),
                FieldMappingRule("sku", FieldMappingSource.SEGMENT, 1),
                FieldMappingRule("quantity", FieldMappingSource.SEGMENT, 2),
            ),
        ),
    )


def _profiles(
    *,
    item_cfg,
    pos_cfg,
    item_source: LabelProfileSource = LabelProfileSource.SUPPLIER,
    position_source: LabelProfileSource = LabelProfileSource.SUPPLIER,
) -> LabelValidationContext:
    return LabelValidationContext(
        resolved_profiles=ResolvedLabelProfiles(
            item=ResolvedLabelProfile(
                label_kind=LabelKind.ITEM,
                source=item_source,
                client_supplier_id="sup-1",
                resolution_source="CLIENT_SUPPLIER",
                extraction_profile_id="item-prof",
                extraction_profile_version=8,
            ),
            position=ResolvedLabelProfile(
                label_kind=LabelKind.POSITION,
                source=position_source,
                client_supplier_id="sup-1",
                resolution_source="CLIENT_SUPPLIER",
                extraction_profile_id="pos-prof",
                extraction_profile_version=3,
            ),
        ),
        item_extraction_configuration=item_cfg,
        position_extraction_configuration=pos_cfg,
        job_id="job-1",
        client_id="client-1",
    )


def _ctx(validation_ctx: LabelValidationContext) -> ImageProcessingContext:
    return ImageProcessingContext(
        job_id="job-1",
        asset_id="asset-1",
        aisle_id="aisle-1",
        inventory_id="inv-1",
        client_id="client-1",
        identification_mode=AisleIdentificationMode.CODE_SCAN,
        execution_strategy=AisleIdentificationExecutionStrategy.CODE_SCAN,
        configuration_snapshot_version=1,
        provider_name=None,
        model_name=None,
        prompt_key=None,
        prompt_version=None,
        attempt_number=1,
        label_validation_context=validation_ctx,
    )


def _asset() -> SourceAsset:
    return SourceAsset(
        id="asset-1",
        aisle_id="aisle-1",
        type=SourceAssetType.PHOTO,
        original_filename="x.jpg",
        storage_path="/tmp/x.jpg",
        mime_type="image/jpeg",
        uploaded_at=_NOW,
        upload_client_file_id="cf1",
    )


def _strategy(value: str, *, repo=None) -> CodeScanProcessingStrategy:
    return CodeScanProcessingStrategy(
        scanner=_Scanner(value),
        content_reader=_Reader(),
        parser=EncodedLabelPayloadParser(quantity_max=9999),
        consolidator=CodeDetectionConsolidator(),
        config=CodeScanConfig(quantity_max=9999, timeout_seconds=5),
        issued_label_resolver=MagicMock(),
        label_validation_service=LabelValidationService(),
        position_detection=None,
        position_label_detection_repo=repo,
    )


def test_get_active_by_kind_resolves_independently() -> None:
    repo = MemorySupplierExtractionProfileRepository()
    for kind, pid, version in (
        (LabelKind.ITEM, "item-v8", 8),
        (LabelKind.POSITION, "pos-v3", 3),
    ):
        repo.save(
            SupplierExtractionProfile(
                id=pid,
                client_id="c1",
                supplier_id="sup1",
                profile_key="default",
                version=version,
                status=ExtractionProfileStatus.ACTIVE,
                configuration=minimal_supplier_item_configuration(),
                visual_notes=None,
                created_by=None,
                created_at=_NOW,
                updated_at=_NOW,
                label_kind=kind,
            )
        )
    item = repo.get_active_by_kind("c1", "sup1", LabelKind.ITEM)
    pos = repo.get_active_by_kind("c1", "sup1", LabelKind.POSITION)
    assert item is not None and item.version == 8
    assert pos is not None and pos.version == 3


def test_activate_extraction_profile_wires_supplier_label_profile() -> None:
    profile_repo = MemorySupplierExtractionProfileRepository()
    label_repo = MemoryClientSupplierLabelProfileRepository()
    profile_repo.save(
        SupplierExtractionProfile(
            id="pos-v3",
            client_id="c1",
            supplier_id="sup1",
            profile_key="default",
            version=3,
            status=ExtractionProfileStatus.DRAFT,
            configuration=_position_segmented_config(),
            visual_notes=None,
            created_by=None,
            created_at=_NOW,
            updated_at=_NOW,
            label_kind=LabelKind.POSITION,
        )
    )
    uc = ActivateSupplierExtractionProfileVersionUseCase(
        client_repo=MagicMock(),
        client_supplier_repo=MagicMock(),
        profile_repo=profile_repo,
        clock=_FixedClock(),
        label_profile_repo=label_repo,
    )
    uc._client_repo.get_by_id = MagicMock(return_value=MagicMock())
    uc._client_supplier_repo.get_by_id = MagicMock(
        return_value=MagicMock(client_id="c1", id="sup1")
    )
    activated = uc.execute(
        ActivateSupplierExtractionProfileVersionCommand(
            client_id="c1",
            supplier_id="sup1",
            profile_id="pos-v3",
            effective_source=LabelProfileSource.SUPPLIER,
        )
    )
    assert activated.status is ExtractionProfileStatus.ACTIVE
    wired = label_repo.get_by_supplier_and_kind("sup1", LabelKind.POSITION)
    assert wired is not None
    assert wired.source is LabelProfileSource.SUPPLIER


def test_position_segmented_payload_never_missing_quantity() -> None:
    repo = MemoryImagePositionLabelDetectionRepository()
    ctx = _profiles(
        item_cfg=_item_segmented_config(),
        pos_cfg=_position_segmented_config(),
    )
    result = _strategy("A04-R-02|04|RIGHT|02", repo=repo).process(_ctx(ctx), _asset())
    assert result.status is ImageResultStatus.RESOLVED_INTERNAL
    assert result.error_code != "MISSING_QUANTITY"
    assert (result.evidence or {}).get("result_kind") == "POSITION_ONLY"
    stored = list(repo.list_by_asset("job-1", "asset-1"))
    assert len(stored) == 1
    assert stored[0].public_identifier == "A04-R-02"
    assert stored[0].metadata_json.get("pallet") == "04"
    assert stored[0].metadata_json.get("side") == "RIGHT"
    assert stored[0].metadata_json.get("level") == "02"


def test_item_segmented_payload_resolves_quantity() -> None:
    item_cfg = _item_segmented_config()
    pos_cfg = ExtractionProfileConfiguration(
        configuration_schema_version=CONFIGURATION_SCHEMA_VERSION_V2,
        required_fields=("position_id",),
        accepted_barcode_formats=("QR",),
        deterministic=DeterministicBarcodeRules(
            field_mappings=(FieldMappingRule("position_id", FieldMappingSource.WHOLE),),
            expected_prefix="NEVER-POS",
        ),
    )
    ctx = _profiles(item_cfg=item_cfg, pos_cfg=pos_cfg)
    result = _strategy("LPNA000184|SKU773421|24").process(_ctx(ctx), _asset())
    assert result.status is ImageResultStatus.RESOLVED_INTERNAL
    assert result.product_results[0].label_id == "LPNA000184"
    assert result.product_results[0].internal_code == "SKU773421"
    assert result.product_results[0].quantity == 24


def test_minimal_item_identity_only_without_quantity() -> None:
    item_cfg = minimal_supplier_item_configuration(expected_prefix="LPNA", exact_length=10)
    pos_cfg = ExtractionProfileConfiguration(
        configuration_schema_version=CONFIGURATION_SCHEMA_VERSION_V2,
        required_fields=("position_id",),
        accepted_barcode_formats=("QR",),
        deterministic=DeterministicBarcodeRules(
            field_mappings=(FieldMappingRule("position_id", FieldMappingSource.WHOLE),),
            expected_prefix="NEVER-POS",
        ),
    )
    ctx = _profiles(item_cfg=item_cfg, pos_cfg=pos_cfg)
    result = _strategy("LPNA000184").process(_ctx(ctx), _asset())
    assert result.status is ImageResultStatus.RESOLVED_INTERNAL
    assert result.error_code != "MISSING_QUANTITY"
    assert result.product_results[0].label_id == "LPNA000184"
    assert result.product_results[0].internal_code is None
    assert result.product_results[0].quantity is None


def test_supplier_wired_invalid_payload_not_legacy_missing_quantity() -> None:
    ctx = _profiles(
        item_cfg=_item_segmented_config(),
        pos_cfg=_position_segmented_config(),
    )
    result = _strategy("GARBAGE-NO-SEGMENTS").process(_ctx(ctx), _asset())
    assert result.error_code != "MISSING_QUANTITY"
    assert result.error_code in {
        "SUPPLIER_PAYLOAD_NOT_RECOGNIZED",
        "SUPPLIER_LABEL_REJECTED",
        "LABEL_PREFIX_MISMATCH",
        "LABEL_SEGMENT_COUNT_MISMATCH",
        "LABEL_FIELD_MAPPING_INVALID",
    }


def test_create_and_activate_wires_label_profile() -> None:
    profile_repo = MemorySupplierExtractionProfileRepository()
    label_repo = MemoryClientSupplierLabelProfileRepository()
    uc = CreateSupplierExtractionProfileVersionUseCase(
        client_repo=MagicMock(),
        client_supplier_repo=MagicMock(),
        profile_repo=profile_repo,
        clock=_FixedClock(),
        label_profile_repo=label_repo,
    )
    uc._client_repo.get_by_id = MagicMock(return_value=MagicMock())
    uc._client_supplier_repo.get_by_id = MagicMock(
        return_value=MagicMock(client_id="c1", id="sup1")
    )
    created = uc.execute(
        CreateSupplierExtractionProfileVersionCommand(
            client_id="c1",
            supplier_id="sup1",
            configuration=_position_segmented_config().to_public_dict(),
            activate=True,
            label_kind=LabelKind.POSITION,
            effective_source=LabelProfileSource.SUPPLIER,
        )
    )
    assert created.status is ExtractionProfileStatus.ACTIVE
    wired = label_repo.get_by_supplier_and_kind("sup1", LabelKind.POSITION)
    assert wired is not None and wired.source is LabelProfileSource.SUPPLIER


def test_create_draft_does_not_change_effective_source() -> None:
    profile_repo = MemorySupplierExtractionProfileRepository()
    label_repo = MemoryClientSupplierLabelProfileRepository()
    uc = CreateSupplierExtractionProfileVersionUseCase(
        client_repo=MagicMock(),
        client_supplier_repo=MagicMock(),
        profile_repo=profile_repo,
        clock=_FixedClock(),
        label_profile_repo=label_repo,
    )
    uc._client_repo.get_by_id = MagicMock(return_value=MagicMock())
    uc._client_supplier_repo.get_by_id = MagicMock(
        return_value=MagicMock(client_id="c1", id="sup1")
    )
    created = uc.execute(
        CreateSupplierExtractionProfileVersionCommand(
            client_id="c1",
            supplier_id="sup1",
            configuration=_position_segmented_config().to_public_dict(),
            activate=False,
            label_kind=LabelKind.POSITION,
            effective_source=LabelProfileSource.SUPPLIER,
        )
    )
    assert created.status is ExtractionProfileStatus.DRAFT
    assert not label_repo.list_by_supplier("sup1")


class _FailingLabelProfileRepository(MemoryClientSupplierLabelProfileRepository):
    def upsert(self, profile):  # type: ignore[override]
        raise RuntimeError("label_profile_repo.upsert failed")


def test_activate_wiring_failure_rolls_back_profile_activation() -> None:
    profile_repo = MemorySupplierExtractionProfileRepository()
    label_repo = _FailingLabelProfileRepository()
    for pid, version, status in (("item-v2", 2, ExtractionProfileStatus.ACTIVE), ("item-v3", 3, ExtractionProfileStatus.DRAFT)):
        profile_repo.save(
            SupplierExtractionProfile(
                id=pid,
                client_id="c1",
                supplier_id="sup1",
                profile_key="default",
                version=version,
                status=status,
                configuration=minimal_supplier_item_configuration(),
                visual_notes=None,
                created_by=None,
                created_at=_NOW,
                updated_at=_NOW,
                label_kind=LabelKind.ITEM,
            )
        )
    uc = ActivateSupplierExtractionProfileVersionUseCase(
        client_repo=MagicMock(),
        client_supplier_repo=MagicMock(),
        profile_repo=profile_repo,
        clock=_FixedClock(),
        label_profile_repo=label_repo,
    )
    uc._client_repo.get_by_id = MagicMock(return_value=MagicMock())
    uc._client_supplier_repo.get_by_id = MagicMock(
        return_value=MagicMock(client_id="c1", id="sup1")
    )
    with pytest.raises(RuntimeError, match="label_profile_repo.upsert failed"):
        uc.execute(
            ActivateSupplierExtractionProfileVersionCommand(
                client_id="c1",
                supplier_id="sup1",
                profile_id="item-v3",
                effective_source=LabelProfileSource.SUPPLIER,
            )
        )
    assert profile_repo.get_by_id("item-v2").status is ExtractionProfileStatus.ACTIVE
    assert profile_repo.get_by_id("item-v3").status is ExtractionProfileStatus.DRAFT


def test_upsert_effective_label_source_idempotent() -> None:
    label_repo = MemoryClientSupplierLabelProfileRepository()
    upsert_effective_label_source(
        label_profile_repo=label_repo,
        clock=_FixedClock(),
        client_supplier_id="sup1",
        label_kind=LabelKind.ITEM,
        source=LabelProfileSource.SUPPLIER,
    )
    upsert_effective_label_source(
        label_profile_repo=label_repo,
        clock=_FixedClock(),
        client_supplier_id="sup1",
        label_kind=LabelKind.ITEM,
        source=LabelProfileSource.SUPPLIER,
    )
    rows = label_repo.list_by_supplier("sup1")
    assert len(rows) == 1
    assert rows[0].source is LabelProfileSource.SUPPLIER


def test_wiring_mismatch_skips_explicit_dinamic_choice() -> None:
    warnings = detect_supplier_wiring_mismatch(
        client_supplier_id="sup1",
        item_source=LabelProfileSource.DINAMIC,
        position_source=LabelProfileSource.DINAMIC,
        active_extraction_kinds={LabelKind.ITEM},
        explicit_wiring_kinds={LabelKind.ITEM},
    )
    assert warnings == []


def test_item_dinamic_d1_not_blocked_by_position_supplier_rejection() -> None:
    from src.application.ports.issued_product_label_repository import IssuedProductLabel
    from src.application.services.product_labels.issued_product_label_resolver import (
        IssuedProductLabelResolver,
    )
    from src.domain.product_labels.format import parse_product_label_payload
    from src.infrastructure.repositories.memory_issued_product_label_repository import (
        MemoryIssuedProductLabelRepository,
    )

    label_id = generate_product_label_id()
    d1 = build_product_label_payload(
        label_id=label_id, internal_code="SKU1", quantity=2
    )
    parsed = parse_product_label_payload(d1)
    issued_repo = MemoryIssuedProductLabelRepository()
    issued_repo.save(
        IssuedProductLabel(
            id="iss-1",
            client_id="client-1",
            label_id=label_id,
            internal_code="SKU1",
            quantity=2,
            format_version="D1",
            checksum=str(parsed.checksum_received),
            payload=d1,
            created_at=_NOW,
        )
    )
    pos_cfg = _position_segmented_config()
    ctx = LabelValidationContext(
        resolved_profiles=ResolvedLabelProfiles(
            item=ResolvedLabelProfile(
                label_kind=LabelKind.ITEM,
                source=LabelProfileSource.DINAMIC,
                client_supplier_id="sup-1",
                resolution_source="CLIENT_SUPPLIER",
            ),
            position=ResolvedLabelProfile(
                label_kind=LabelKind.POSITION,
                source=LabelProfileSource.SUPPLIER,
                client_supplier_id="sup-1",
                resolution_source="CLIENT_SUPPLIER",
                extraction_profile_id="pos-prof",
                extraction_profile_version=3,
            ),
        ),
        item_extraction_configuration=None,
        position_extraction_configuration=pos_cfg,
        job_id="job-1",
        client_id="client-1",
    )
    strategy = CodeScanProcessingStrategy(
        scanner=_Scanner(d1),
        content_reader=_Reader(),
        parser=EncodedLabelPayloadParser(quantity_max=9999),
        consolidator=CodeDetectionConsolidator(),
        config=CodeScanConfig(quantity_max=9999, timeout_seconds=5),
        issued_label_resolver=IssuedProductLabelResolver(issued_repo=issued_repo),
        label_validation_service=LabelValidationService(),
        position_detection=None,
        position_label_detection_repo=None,
    )
    result = strategy.process(_ctx(ctx), _asset())
    assert result.status is ImageResultStatus.RESOLVED_INTERNAL
    assert result.error_code != "MISSING_QUANTITY"


def test_pruebas_b_productive_segmented_payloads() -> None:
    """Regression: exact configs persisted for ClientSupplier pruebas b."""
    from src.application.services.supplier_extraction_profiles.pruebas_b_segmented_configurations import (
        pruebas_b_item_segmented_configuration,
        pruebas_b_position_segmented_configuration,
    )

    item_cfg = pruebas_b_item_segmented_configuration()
    pos_cfg = pruebas_b_position_segmented_configuration()
    ctx = _profiles(item_cfg=item_cfg, pos_cfg=pos_cfg)

    repo = MemoryImagePositionLabelDetectionRepository()
    pos_scan = _strategy("A04-R-02|04|RIGHT|02", repo=repo).process(_ctx(ctx), _asset())
    assert pos_scan.status is ImageResultStatus.RESOLVED_INTERNAL
    assert pos_scan.error_code != "MISSING_QUANTITY"
    assert (pos_scan.evidence or {}).get("result_kind") == "POSITION_ONLY"
    stored = list(repo.list_by_asset("job-1", "asset-1"))
    assert stored[0].public_identifier == "A04-R-02"
    assert stored[0].metadata_json.get("pallet") == "04"
    assert stored[0].metadata_json.get("side") == "RIGHT"
    assert stored[0].metadata_json.get("level") == "02"

    item_scan = _strategy("LPNA000184|SKU773421|24").process(_ctx(ctx), _asset())
    assert item_scan.status is ImageResultStatus.RESOLVED_INTERNAL
    assert item_scan.error_code != "MISSING_QUANTITY"
    assert item_scan.product_results[0].label_id == "LPNA000184"
    assert item_scan.product_results[0].internal_code == "SKU773421"
    assert item_scan.product_results[0].quantity == 24
