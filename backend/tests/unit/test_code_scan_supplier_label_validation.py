"""CODE_SCAN uses LabelValidationService for SUPPLIER ITEM (Phase 2)."""

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
from src.domain.client_supplier.extraction_profile import ExtractionProfileConfiguration
from src.domain.code_scans.entities import CodeType
from src.domain.image_processing.contracts import ImageProcessingContext, ImageResultStatus
from src.domain.label_profiles.entities import ResolvedLabelProfile, ResolvedLabelProfiles
from src.domain.label_profiles.kinds import LabelKind, LabelProfileSource

_NOW = datetime(2026, 8, 31, 12, 0, 0, tzinfo=timezone.utc)


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
                metadata_json={"pyzbar_type": "CODE128"},
            )
        ]


def _context(*, validation_ctx: LabelValidationContext) -> ImageProcessingContext:
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


def _strategy(scanner_value: str) -> CodeScanProcessingStrategy:
    parser = EncodedLabelPayloadParser(quantity_max=9999)
    return CodeScanProcessingStrategy(
        scanner=_Scanner(scanner_value),
        content_reader=_Reader(),
        parser=parser,
        consolidator=CodeDetectionConsolidator(),
        config=CodeScanConfig(quantity_max=9999, timeout_seconds=5),
        issued_label_resolver=MagicMock(),
        label_validation_service=LabelValidationService(),
        position_detection=None,
    )


def test_code_scan_supplier_item_resolves_without_issued_registry() -> None:
    profiles = ResolvedLabelProfiles(
        item=ResolvedLabelProfile(
            label_kind=LabelKind.ITEM,
            source=LabelProfileSource.SUPPLIER,
            client_supplier_id="sup-1",
            resolution_source="CLIENT_SUPPLIER",
        ),
        position=ResolvedLabelProfile(
            label_kind=LabelKind.POSITION,
            source=LabelProfileSource.DINAMIC,
            client_supplier_id="sup-1",
            resolution_source="DEFAULT",
        ),
    )
    ctx = LabelValidationContext(
        resolved_profiles=profiles,
        item_extraction_configuration=ExtractionProfileConfiguration(
            accepted_barcode_formats=("CODE128",),
            custom_payload_pattern=r"^SUP[0-9]{8}$",
            required_fields=("internal_code",),
        ),
        job_id="job-1",
        client_id="client-1",
    )
    result = _strategy("SUP12345678").process(_context(validation_ctx=ctx), _asset())
    assert result.status is ImageResultStatus.RESOLVED_INTERNAL
    assert len(result.product_results) == 1
    assert result.product_results[0].internal_code == "SUP12345678"
    assert result.product_results[0].format_version == "SUPPLIER"


def test_code_scan_legacy_without_label_profiles_still_runs_dinamic_path() -> None:
    """No snapshot → DINAMIC default; non-D1 payload must not crash."""
    result = _strategy("PLAIN-SKU|2").process(
        _context(validation_ctx=LabelValidationContext(resolved_profiles=None)),
        _asset(),
    )
    assert result.status in (
        ImageResultStatus.RESOLVED_INTERNAL,
        ImageResultStatus.PENDING_MANUAL_REVIEW,
        ImageResultStatus.UNRECOGNIZED,
    )
