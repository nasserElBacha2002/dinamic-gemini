"""Real QR decode + SUPPLIER SEGMENTED profile (identity rules on label_id)."""

from __future__ import annotations

import io
from datetime import datetime, timezone

import pytest

pytest.importorskip("pyzbar")
qrcode = pytest.importorskip("qrcode")

from src.application.services.image_processing.code_detection_consolidator import (  # noqa: E402
    CodeDetectionConsolidator,
)
from src.application.services.image_processing.code_scan_processing_strategy import (  # noqa: E402
    CodeScanConfig,
    CodeScanProcessingStrategy,
)
from src.application.services.image_processing.encoded_label_payload_parser import (  # noqa: E402
    EncodedLabelPayloadParser,
)
from src.application.services.label_validation import (  # noqa: E402
    LabelValidationContext,
    LabelValidationService,
)
from src.domain.aisle_identification.modes import (  # noqa: E402
    CONFIGURATION_SNAPSHOT_VERSION,
    AisleIdentificationExecutionStrategy,
    AisleIdentificationMode,
)
from src.domain.assets.entities import SourceAsset, SourceAssetType  # noqa: E402
from src.domain.client_supplier.extraction_profile import (  # noqa: E402
    CONFIGURATION_SCHEMA_VERSION_V2,
    CharacterSetPolicy,
    DeterministicBarcodeRules,
    ExtractionProfileConfiguration,
    FieldMappingRule,
    FieldMappingSource,
    PayloadStructure,
    QuantityExtractionRules,
    QuantityPresence,
)
from src.domain.image_processing.contracts import (  # noqa: E402
    ExecutionScope,
    ImageProcessingContext,
    ImageResultStatus,
)
from src.domain.label_profiles.entities import (  # noqa: E402
    ResolvedLabelProfile,
    ResolvedLabelProfiles,
)
from src.domain.label_profiles.kinds import LabelKind, LabelProfileSource  # noqa: E402

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _qr_png_bytes(payload: str) -> bytes:
    img = qrcode.make(payload)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class _FixedContentReader:
    def __init__(self, content: bytes) -> None:
        self._content = content

    def read_image_bytes(self, asset: SourceAsset) -> bytes:
        return self._content


def _strategy(content: bytes) -> CodeScanProcessingStrategy:
    try:
        from src.infrastructure.code_scanning.pyzbar_code_scanner import PyzbarCodeScanner

        scanner = PyzbarCodeScanner()
    except Exception:  # pragma: no cover
        pytest.skip("pyzbar/libzbar not available")
    return CodeScanProcessingStrategy(
        scanner=scanner,
        content_reader=_FixedContentReader(content),
        parser=EncodedLabelPayloadParser(quantity_max=99999999, allow_decimal_quantity=False),
        consolidator=CodeDetectionConsolidator(),
        config=CodeScanConfig(quantity_max=99999999),
        label_validation_service=LabelValidationService(),
    )


def _asset() -> SourceAsset:
    return SourceAsset(
        id="s1",
        aisle_id="a1",
        type=SourceAssetType.PHOTO,
        original_filename="s1.png",
        storage_path="/s1.png",
        mime_type="image/png",
        uploaded_at=NOW,
    )


def _profiles() -> ResolvedLabelProfiles:
    return ResolvedLabelProfiles(
        item=ResolvedLabelProfile(
            label_kind=LabelKind.ITEM,
            source=LabelProfileSource.SUPPLIER,
            client_supplier_id="sup-1",
            resolution_source="CLIENT_SUPPLIER",
            extraction_profile_version=3,
        ),
        position=ResolvedLabelProfile(
            label_kind=LabelKind.POSITION,
            source=LabelProfileSource.SUPPLIER,
            client_supplier_id="sup-1",
            resolution_source="CLIENT_SUPPLIER",
            extraction_profile_version=3,
        ),
    )


def _item_cfg() -> ExtractionProfileConfiguration:
    return ExtractionProfileConfiguration(
        configuration_schema_version=CONFIGURATION_SCHEMA_VERSION_V2,
        required_fields=("label_id", "quantity"),
        accepted_barcode_formats=("QR", "CODE128"),
        quantity_rules=QuantityExtractionRules(
            required=True,
            minimum=1,
            expected_presence=QuantityPresence.ALWAYS,
            allow_external_fallback=False,
        ),
        deterministic=DeterministicBarcodeRules(
            expected_prefix="ASI",
            exact_length=10,
            character_set=CharacterSetPolicy.ALPHANUMERIC_WITH_HYPHEN,
            payload_structure=PayloadStructure.SEGMENTED,
            delimiter="|",
            expected_segment_count=2,
            field_mappings=(
                FieldMappingRule("label_id", FieldMappingSource.SEGMENT, 0),
                FieldMappingRule("quantity", FieldMappingSource.SEGMENT, 1),
            ),
        ),
    )


def _context() -> ImageProcessingContext:
    ctx = LabelValidationContext(
        resolved_profiles=_profiles(),
        item_extraction_configuration=_item_cfg(),
        position_extraction_configuration=ExtractionProfileConfiguration(
            configuration_schema_version=CONFIGURATION_SCHEMA_VERSION_V2,
            required_fields=("position_id",),
            accepted_barcode_formats=("QR",),
            deterministic=DeterministicBarcodeRules(
                expected_prefix="NEVER",
                field_mappings=(FieldMappingRule("position_id", FieldMappingSource.WHOLE),),
            ),
        ),
        job_id="job-seg-qr",
    )
    return ImageProcessingContext(
        job_id="job-seg-qr",
        asset_id="s1",
        aisle_id="a1",
        inventory_id="inv1",
        client_id="client-1",
        identification_mode=AisleIdentificationMode.CODE_SCAN,
        execution_strategy=AisleIdentificationExecutionStrategy.CODE_SCAN,
        configuration_snapshot_version=CONFIGURATION_SNAPSHOT_VERSION,
        provider_name="code_scan",
        model_name="pyzbar",
        prompt_key=None,
        prompt_version=None,
        attempt_number=1,
        execution_scope=ExecutionScope.SINGLE_ASSET,
        label_validation_context=ctx,
    )


@pytest.mark.parametrize(
    ("payload", "qty"),
    [
        ("ASI-7K2M9Q|24", 24),
        ("ASI-4F8N3C|12", 12),
        ("ASI-9T6R2V|48", 48),
        ("ASI-2W5H8D|6", 6),
    ],
)
def test_real_qr_segmented_item_quantities(payload: str, qty: int) -> None:
    result = _strategy(_qr_png_bytes(payload)).process(_context(), _asset())
    assert result.status is ImageResultStatus.RESOLVED_INTERNAL
    assert result.error_code not in {"LABEL_LENGTH_MISMATCH", "MISSING_QUANTITY"}
    assert result.quantity == qty
    assert result.product_results
    assert int(result.product_results[0].quantity or 0) == qty


def test_real_qr_four_segmented_items_total_90() -> None:
    payloads = (
        ("ASI-7K2M9Q|24", 24),
        ("ASI-4F8N3C|12", 12),
        ("ASI-9T6R2V|48", 48),
        ("ASI-2W5H8D|6", 6),
    )
    total = 0
    for payload, qty in payloads:
        result = _strategy(_qr_png_bytes(payload)).process(_context(), _asset())
        assert result.status is ImageResultStatus.RESOLVED_INTERNAL
        total += int(result.quantity or 0)
        assert int(result.quantity or 0) == qty
    assert total == 90
