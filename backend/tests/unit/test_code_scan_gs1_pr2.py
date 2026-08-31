"""PR2 — CODE_SCAN GS1 SSCC/GTIN through scanner → extractor → validator."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

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
from src.domain.aisle_identification.modes import (
    AisleIdentificationExecutionStrategy,
    AisleIdentificationMode,
)
from src.domain.assets.entities import SourceAsset, SourceAssetType
from src.domain.client_supplier.extraction_profile import (
    CONFIGURATION_SCHEMA_VERSION_V2,
    DeterministicBarcodeRules,
    ExtractionProfileConfiguration,
    FieldMappingRule,
    FieldMappingSource,
    ItemLabelSemanticType,
    PayloadStructure,
    QuantityExtractionRules,
)
from src.domain.code_scans.entities import CodeType
from src.domain.image_processing.contracts import ImageProcessingContext, ImageResultStatus
from src.domain.label_profiles.entities import ResolvedLabelProfile, ResolvedLabelProfiles
from src.domain.label_profiles.kinds import LabelKind, LabelProfileSource

_NOW = datetime(2026, 8, 31, 12, 0, 0, tzinfo=timezone.utc)
_VALID_SSCC = "000123456700000008"
_VALID_GTIN14 = "09521234500001"


class _Reader:
    def read_image_bytes(self, asset: SourceAsset) -> bytes:
        return b"fake-image"


class _Scanner:
    def __init__(self, *values: str) -> None:
        self._values = values

    @property
    def engine_name(self) -> str:
        return "test"

    def scan_asset(self, asset, content=None):
        return [
            CodeScanDetectionCandidate(
                code_type=CodeType.BARCODE,
                code_value=v,
                confidence=1.0,
                bounding_box_json=None,
                metadata_json={"pyzbar_type": "CODE128"},
            )
            for v in self._values
        ]


def _profiles() -> ResolvedLabelProfiles:
    return ResolvedLabelProfiles(
        item=ResolvedLabelProfile(
            label_kind=LabelKind.ITEM,
            source=LabelProfileSource.SUPPLIER,
            client_supplier_id="sup-1",
            resolution_source="CLIENT_SUPPLIER",
            extraction_profile_version=1,
        ),
        position=ResolvedLabelProfile(
            label_kind=LabelKind.POSITION,
            source=LabelProfileSource.SUPPLIER,
            client_supplier_id="sup-1",
            resolution_source="CLIENT_SUPPLIER",
            extraction_profile_version=1,
        ),
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


def _strategy(*values: str) -> CodeScanProcessingStrategy:
    return CodeScanProcessingStrategy(
        scanner=_Scanner(*values),
        content_reader=_Reader(),
        parser=EncodedLabelPayloadParser(quantity_max=9999),
        consolidator=CodeDetectionConsolidator(),
        config=CodeScanConfig(quantity_max=9999, timeout_seconds=5),
        issued_label_resolver=MagicMock(),
        label_validation_service=LabelValidationService(),
        position_detection=None,
        position_label_detection_repo=None,
    )


def test_code_scan_gs1_sscc_label_id_no_sku_no_quantity() -> None:
    item_cfg = ExtractionProfileConfiguration(
        configuration_schema_version=CONFIGURATION_SCHEMA_VERSION_V2,
        semantic_type=ItemLabelSemanticType.SSCC.value,
        required_fields=("label_id",),
        accepted_barcode_formats=("CODE128",),
        quantity_rules=QuantityExtractionRules(required=False, minimum=1),
        deterministic=DeterministicBarcodeRules(
            payload_structure=PayloadStructure.GS1,
            required_application_identifiers=("00",),
            field_mappings=(
                FieldMappingRule(
                    "label_id",
                    FieldMappingSource.APPLICATION_IDENTIFIER,
                    application_identifier="00",
                ),
            ),
        ),
    )
    pos_cfg = ExtractionProfileConfiguration(
        configuration_schema_version=CONFIGURATION_SCHEMA_VERSION_V2,
        required_fields=("position_id",),
        accepted_barcode_formats=("CODE128",),
        deterministic=DeterministicBarcodeRules(
            expected_prefix="NEVER",
            field_mappings=(FieldMappingRule("position_id", FieldMappingSource.WHOLE),),
        ),
    )
    ctx = LabelValidationContext(
        resolved_profiles=_profiles(),
        item_extraction_configuration=item_cfg,
        position_extraction_configuration=pos_cfg,
        job_id="job-1",
    )
    result = _strategy(f"(00){_VALID_SSCC}").process(_ctx(ctx), _asset())
    assert result.product_results
    product = result.product_results[0]
    assert product.label_id == _VALID_SSCC
    assert product.internal_code is None
    assert product.quantity is None
    assert product.logistic_unit_id == _VALID_SSCC
    assert product.format_version == "SUPPLIER_LOGISTIC_UNIT"
    assert product.semantic_type == "SSCC"
    # Inventory still requires SKU+qty for RESOLVED_INTERNAL — logistic units stay reviewable.
    assert result.status is ImageResultStatus.PENDING_MANUAL_REVIEW


def test_code_scan_lpn_simple_label_id_no_sku() -> None:
    item_cfg = ExtractionProfileConfiguration(
        configuration_schema_version=CONFIGURATION_SCHEMA_VERSION_V2,
        semantic_type=ItemLabelSemanticType.LPN.value,
        required_fields=("label_id",),
        accepted_barcode_formats=("CODE128",),
        quantity_rules=QuantityExtractionRules(required=False, minimum=1),
        deterministic=DeterministicBarcodeRules(
            payload_structure=PayloadStructure.SIMPLE,
            field_mappings=(FieldMappingRule("label_id", FieldMappingSource.WHOLE),),
        ),
    )
    pos_cfg = ExtractionProfileConfiguration(
        configuration_schema_version=CONFIGURATION_SCHEMA_VERSION_V2,
        required_fields=("position_id",),
        accepted_barcode_formats=("CODE128",),
        deterministic=DeterministicBarcodeRules(
            expected_prefix="NEVER",
            field_mappings=(FieldMappingRule("position_id", FieldMappingSource.WHOLE),),
        ),
    )
    ctx = LabelValidationContext(
        resolved_profiles=_profiles(),
        item_extraction_configuration=item_cfg,
        position_extraction_configuration=pos_cfg,
        job_id="job-1",
    )
    result = _strategy("LPN-42-ALPHA").process(_ctx(ctx), _asset())
    assert result.product_results
    product = result.product_results[0]
    assert product.label_id == "LPN-42-ALPHA"
    assert product.internal_code is None
    assert product.quantity is None
    assert product.logistic_unit_id == "LPN-42-ALPHA"
    assert product.semantic_type == "LPN"
    assert result.status is ImageResultStatus.PENDING_MANUAL_REVIEW


def test_sscc_e2e_materialization_limitation_documented() -> None:
    """
    ClientSupplier SSCC profile → CODE_SCAN → GS1 → extractor → validation →
    ProcessedProductLabel(logistic_unit). ProductRecord/SKU inventory rows are NOT
    auto-created until a logistic-unit persistence model exists.
    """
    item_cfg = ExtractionProfileConfiguration(
        configuration_schema_version=CONFIGURATION_SCHEMA_VERSION_V2,
        semantic_type=ItemLabelSemanticType.SSCC.value,
        required_fields=("label_id",),
        accepted_barcode_formats=("CODE128",),
        quantity_rules=QuantityExtractionRules(required=False, minimum=1),
        deterministic=DeterministicBarcodeRules(
            payload_structure=PayloadStructure.GS1,
            required_application_identifiers=("00",),
            field_mappings=(
                FieldMappingRule(
                    "label_id",
                    FieldMappingSource.APPLICATION_IDENTIFIER,
                    application_identifier="00",
                ),
            ),
        ),
    )
    ctx = LabelValidationContext(
        resolved_profiles=_profiles(),
        item_extraction_configuration=item_cfg,
        position_extraction_configuration=None,
        job_id="job-sscc-e2e",
    )
    result = _strategy(f"(00){_VALID_SSCC}").process(_ctx(ctx), _asset())
    assert result.status is ImageResultStatus.PENDING_MANUAL_REVIEW
    assert result.product_results
    product = result.product_results[0]
    assert product.label_id == _VALID_SSCC
    assert product.internal_code is None
    assert product.quantity is None
    assert (result.evidence or {}).get("logistic_unit_review") is True
    assert "LOGISTIC_UNIT_NO_PRODUCT_RECORD" in str(
        (result.evidence or {}).get("limitation", "")
    )
    # Explicit product limitation: no invent of SKU for SSCC; SQL ProductRecord path not used.


def test_code_scan_gs1_gtin_with_lot_maps_sku() -> None:
    item_cfg = ExtractionProfileConfiguration(
        configuration_schema_version=CONFIGURATION_SCHEMA_VERSION_V2,
        semantic_type=ItemLabelSemanticType.PRODUCT_SKU.value,
        required_fields=("sku",),
        accepted_barcode_formats=("CODE128",),
        quantity_rules=QuantityExtractionRules(required=False, minimum=1),
        deterministic=DeterministicBarcodeRules(
            payload_structure=PayloadStructure.GS1,
            required_application_identifiers=("01",),
            optional_application_identifiers=("10",),
            field_mappings=(
                FieldMappingRule(
                    "sku",
                    FieldMappingSource.APPLICATION_IDENTIFIER,
                    application_identifier="01",
                ),
                FieldMappingRule(
                    "lot",
                    FieldMappingSource.APPLICATION_IDENTIFIER,
                    application_identifier="10",
                ),
            ),
        ),
    )
    pos_cfg = ExtractionProfileConfiguration(
        configuration_schema_version=CONFIGURATION_SCHEMA_VERSION_V2,
        required_fields=("position_id",),
        accepted_barcode_formats=("CODE128",),
        deterministic=DeterministicBarcodeRules(
            expected_prefix="NEVER",
            field_mappings=(FieldMappingRule("position_id", FieldMappingSource.WHOLE),),
        ),
    )
    ctx = LabelValidationContext(
        resolved_profiles=_profiles(),
        item_extraction_configuration=item_cfg,
        position_extraction_configuration=pos_cfg,
        job_id="job-1",
    )
    result = _strategy(f"(01){_VALID_GTIN14}(10)LOT9").process(_ctx(ctx), _asset())
    assert result.product_results
    product = result.product_results[0]
    assert product.internal_code == _VALID_GTIN14
    assert product.quantity is None
