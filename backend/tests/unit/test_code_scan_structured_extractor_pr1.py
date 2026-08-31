"""PR1 — CODE_SCAN uses StructuredPayloadExtractor (no raw=sku assumption)."""

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
    PayloadStructure,
    QuantityExtractionRules,
)
from src.domain.code_scans.entities import CodeType
from src.domain.image_processing.contracts import ImageProcessingContext, ImageResultStatus
from src.domain.label_profiles.entities import ResolvedLabelProfile, ResolvedLabelProfiles
from src.domain.label_profiles.kinds import LabelKind, LabelProfileSource
from src.infrastructure.repositories.memory_image_position_label_detection_repository import (
    MemoryImagePositionLabelDetectionRepository,
)

_NOW = datetime(2026, 8, 31, 12, 0, 0, tzinfo=timezone.utc)


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


def _ctx(validation_ctx: LabelValidationContext, *, job_id: str = "job-1") -> ImageProcessingContext:
    return ImageProcessingContext(
        job_id=job_id,
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


def _strategy(*values: str, repo=None) -> CodeScanProcessingStrategy:
    return CodeScanProcessingStrategy(
        scanner=_Scanner(*values),
        content_reader=_Reader(),
        parser=EncodedLabelPayloadParser(quantity_max=9999),
        consolidator=CodeDetectionConsolidator(),
        config=CodeScanConfig(quantity_max=9999, timeout_seconds=5),
        issued_label_resolver=MagicMock(),
        label_validation_service=LabelValidationService(),
        position_detection=None,
        position_label_detection_repo=repo,
    )


def test_code_scan_simple_item_whole_to_sku() -> None:
    item_cfg = ExtractionProfileConfiguration(
        configuration_schema_version=CONFIGURATION_SCHEMA_VERSION_V2,
        required_fields=("label_id", "sku"),
        accepted_barcode_formats=("CODE128",),
        quantity_rules=QuantityExtractionRules(required=False, minimum=1),
        deterministic=DeterministicBarcodeRules(
            field_mappings=(
                FieldMappingRule("label_id", FieldMappingSource.WHOLE),
                FieldMappingRule("sku", FieldMappingSource.WHOLE),
            ),
        ),
    )
    pos_cfg = ExtractionProfileConfiguration(
        configuration_schema_version=CONFIGURATION_SCHEMA_VERSION_V2,
        required_fields=("position_id",),
        accepted_barcode_formats=("CODE128",),
        deterministic=DeterministicBarcodeRules(
            field_mappings=(FieldMappingRule("position_id", FieldMappingSource.WHOLE),),
            expected_prefix="NEVER",
        ),
    )
    ctx = LabelValidationContext(
        resolved_profiles=_profiles(),
        item_extraction_configuration=item_cfg,
        position_extraction_configuration=pos_cfg,
        job_id="job-1",
    )
    result = _strategy("SKU-ONLY-99").process(_ctx(ctx), _asset())
    # Quantity not mapped and not defaulted to 1 → manual review, but fields mapped.
    assert result.status in (
        ImageResultStatus.RESOLVED_INTERNAL,
        ImageResultStatus.PENDING_MANUAL_REVIEW,
    )
    assert result.product_results
    assert result.product_results[0].internal_code == "SKU-ONLY-99"
    assert result.product_results[0].label_id == "SKU-ONLY-99"
    assert result.product_results[0].quantity is None


def test_code_scan_simple_position_whole_to_position_id() -> None:
    repo = MemoryImagePositionLabelDetectionRepository()
    item_cfg = ExtractionProfileConfiguration(
        configuration_schema_version=CONFIGURATION_SCHEMA_VERSION_V2,
        required_fields=("sku",),
        accepted_barcode_formats=("CODE128",),
        deterministic=DeterministicBarcodeRules(
            field_mappings=(FieldMappingRule("sku", FieldMappingSource.WHOLE),),
            expected_prefix="NEVER-ITEM",
        ),
    )
    pos_cfg = ExtractionProfileConfiguration(
        configuration_schema_version=CONFIGURATION_SCHEMA_VERSION_V2,
        required_fields=("position_id",),
        accepted_barcode_formats=("CODE128",),
        deterministic=DeterministicBarcodeRules(
            field_mappings=(FieldMappingRule("position_id", FieldMappingSource.WHOLE),),
        ),
    )
    ctx = LabelValidationContext(
        resolved_profiles=_profiles(),
        item_extraction_configuration=item_cfg,
        position_extraction_configuration=pos_cfg,
        job_id="job-1",
    )
    result = _strategy("LOC-42", repo=repo).process(_ctx(ctx), _asset())
    assert result.status is ImageResultStatus.PENDING_MANUAL_REVIEW
    stored = list(repo.list_by_asset("job-1", "asset-1"))
    assert len(stored) == 1
    assert stored[0].public_identifier == "LOC-42"


def test_code_scan_segmented_item_maps_fields_not_raw_sku() -> None:
    item_cfg = ExtractionProfileConfiguration(
        configuration_schema_version=CONFIGURATION_SCHEMA_VERSION_V2,
        required_fields=("label_id", "sku", "quantity"),
        accepted_barcode_formats=("CODE128",),
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
    pos_cfg = ExtractionProfileConfiguration(
        configuration_schema_version=CONFIGURATION_SCHEMA_VERSION_V2,
        required_fields=("position_id",),
        accepted_barcode_formats=("CODE128",),
        deterministic=DeterministicBarcodeRules(
            field_mappings=(FieldMappingRule("position_id", FieldMappingSource.WHOLE),),
            expected_prefix="NEVER",
        ),
    )
    ctx = LabelValidationContext(
        resolved_profiles=_profiles(),
        item_extraction_configuration=item_cfg,
        position_extraction_configuration=pos_cfg,
        job_id="job-1",
    )
    result = _strategy("ABC001|SKU123|20").process(_ctx(ctx), _asset())
    assert result.status is ImageResultStatus.RESOLVED_INTERNAL
    assert len(result.product_results) == 1
    product = result.product_results[0]
    assert product.label_id == "ABC001"
    assert product.internal_code == "SKU123"
    assert product.quantity == 20
    assert product.internal_code != "ABC001|SKU123|20"


def test_code_scan_segmented_position_materializes() -> None:
    repo = MemoryImagePositionLabelDetectionRepository()
    item_cfg = ExtractionProfileConfiguration(
        configuration_schema_version=CONFIGURATION_SCHEMA_VERSION_V2,
        required_fields=("sku",),
        accepted_barcode_formats=("CODE128",),
        deterministic=DeterministicBarcodeRules(
            field_mappings=(FieldMappingRule("sku", FieldMappingSource.WHOLE),),
            expected_prefix="NEVER-ITEM",
        ),
    )
    pos_cfg = ExtractionProfileConfiguration(
        configuration_schema_version=CONFIGURATION_SCHEMA_VERSION_V2,
        required_fields=("position_id",),
        accepted_barcode_formats=("CODE128",),
        deterministic=DeterministicBarcodeRules(
            payload_structure=PayloadStructure.SEGMENTED,
            delimiter="|",
            expected_segment_count=3,
            field_mappings=(
                FieldMappingRule("position_id", FieldMappingSource.SEGMENT, 0),
                FieldMappingRule("pallet", FieldMappingSource.SEGMENT, 1),
                FieldMappingRule("side", FieldMappingSource.SEGMENT, 2),
            ),
        ),
    )
    ctx = LabelValidationContext(
        resolved_profiles=_profiles(),
        item_extraction_configuration=item_cfg,
        position_extraction_configuration=pos_cfg,
        job_id="job-1",
    )
    result = _strategy("POS001|04|RIGHT", repo=repo).process(_ctx(ctx), _asset())
    assert result.status is ImageResultStatus.PENDING_MANUAL_REVIEW
    stored = list(repo.list_by_asset("job-1", "asset-1"))
    assert len(stored) == 1
    assert stored[0].public_identifier == "POS001"
    assert stored[0].metadata_json.get("pallet") == "04"


def test_code_scan_snapshot_delimiter_v1_vs_v2() -> None:
    def _cfg(delimiter: str) -> ExtractionProfileConfiguration:
        return ExtractionProfileConfiguration(
            configuration_schema_version=CONFIGURATION_SCHEMA_VERSION_V2,
            required_fields=("sku", "quantity"),
            accepted_barcode_formats=("CODE128",),
            quantity_rules=QuantityExtractionRules(required=True, minimum=1),
            deterministic=DeterministicBarcodeRules(
                payload_structure=PayloadStructure.SEGMENTED,
                delimiter=delimiter,
                expected_segment_count=2,
                field_mappings=(
                    FieldMappingRule("sku", FieldMappingSource.SEGMENT, 0),
                    FieldMappingRule("quantity", FieldMappingSource.SEGMENT, 1),
                ),
            ),
        )

    v1 = LabelValidationContext(
        resolved_profiles=_profiles(),
        item_extraction_configuration=_cfg("|"),
        position_extraction_configuration=_cfg("-"),
        job_id="job-a",
    )
    v2 = LabelValidationContext(
        resolved_profiles=_profiles(),
        item_extraction_configuration=_cfg("-"),
        position_extraction_configuration=_cfg("|"),
        job_id="job-b",
    )
    a = _strategy("SKU1|5").process(_ctx(v1, job_id="job-a"), _asset())
    b = _strategy("SKU1|5").process(_ctx(v2, job_id="job-b"), _asset())
    assert a.status is ImageResultStatus.RESOLVED_INTERNAL
    assert a.product_results[0].internal_code == "SKU1"
    assert a.product_results[0].quantity == 5
    assert b.status is not ImageResultStatus.RESOLVED_INTERNAL
