"""CODE_SCAN must ignore OCR supplier-profile validation rules.

OCR profile rules (exact_length, anchors, printed-text charset, etc.) apply only to
INTERNAL_OCR. CODE_SCAN uses the deterministic parser + consolidator. External AI uses
prompts. Regression coverage for jobs that previously failed when profile_aware routed
barcode/QR through OCR validation (UNSUPPORTED_BARCODE_FORMAT / INVALID_INTERNAL_CODE).
"""

from __future__ import annotations

from datetime import datetime, timezone

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
from src.application.services.image_processing.field_candidate_set import (
    normalize_barcode_format_for_profile,
)
from src.domain.aisle_identification.modes import (
    AisleIdentificationExecutionStrategy,
    AisleIdentificationMode,
)
from src.domain.assets.entities import SourceAsset, SourceAssetType
from src.domain.client_supplier.extraction_profile import default_extraction_configuration
from src.domain.code_scans.entities import CodeScanDetectionStatus, CodeType
from src.domain.image_processing.contracts import (
    ExecutionScope,
    ImageProcessingContext,
    ImageResultStatus,
)


class _FakeScanner:
    engine_name = "fake"

    def __init__(self, pyzbar_type: str, payload: str, code_type: CodeType) -> None:
        self._pyzbar_type = pyzbar_type
        self._payload = payload
        self._code_type = code_type

    def scan_asset(self, asset, content=None):
        return [
            CodeScanDetectionCandidate(
                code_type=self._code_type,
                code_value=self._payload,
                detection_status=CodeScanDetectionStatus.DETECTED,
                metadata_json={"pyzbar_type": self._pyzbar_type},
            )
        ]


class _Reader:
    def read_image_bytes(self, asset) -> bytes:
        return b"image-bytes"


def _context(
    *, profile_aware: bool = True, configuration: dict | None = None
) -> ImageProcessingContext:
    cfg = (
        configuration
        if configuration is not None
        else default_extraction_configuration().to_public_dict()
    )
    return ImageProcessingContext(
        job_id="job1",
        asset_id="asset1",
        aisle_id="a1",
        inventory_id="inv1",
        client_id=None,
        identification_mode=AisleIdentificationMode.CODE_SCAN,
        execution_strategy=AisleIdentificationExecutionStrategy.CODE_SCAN,
        configuration_snapshot_version=1,
        provider_name=None,
        model_name=None,
        prompt_key=None,
        prompt_version=None,
        attempt_number=1,
        execution_scope=ExecutionScope.SINGLE_ASSET,
        profile_aware_validation_enabled=profile_aware,
        supplier_extraction_profile={"configuration": cfg},
    )


def _asset() -> SourceAsset:
    return SourceAsset(
        id="asset1",
        aisle_id="a1",
        type=SourceAssetType.PHOTO,
        original_filename="a.jpg",
        storage_path="/a.jpg",
        mime_type="image/jpeg",
        uploaded_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def _strategy(scanner) -> CodeScanProcessingStrategy:
    return CodeScanProcessingStrategy(
        scanner=scanner,
        content_reader=_Reader(),
        parser=EncodedLabelPayloadParser(quantity_max=99999999),
        consolidator=CodeDetectionConsolidator(),
        config=CodeScanConfig(quantity_max=99999999, enable_rotations=False),
    )


def test_normalize_barcode_format_aliases() -> None:
    assert normalize_barcode_format_for_profile("QR_CODE") == "QR"
    assert normalize_barcode_format_for_profile("QRCODE") == "QR"
    assert normalize_barcode_format_for_profile("CODE_128") == "CODE128"
    assert normalize_barcode_format_for_profile("CODE128") == "CODE128"
    assert normalize_barcode_format_for_profile("EAN_13") == "EAN13"
    assert normalize_barcode_format_for_profile("UPCA") == "UPC_A"


def test_code_scan_resolves_with_profile_aware_flag_enabled() -> None:
    """profile_aware must not divert CODE_SCAN into OCR profile validation."""
    strategy = _strategy(_FakeScanner("QRCODE", "ABC|5", CodeType.QR))
    result = strategy.process(_context(profile_aware=True), _asset())
    assert result.status is ImageResultStatus.RESOLVED_INTERNAL
    assert result.internal_code == "ABC"
    assert result.quantity == 5.0
    assert result.error_code is None
    assert not (result.evidence or {}).get("profile_validation_executed")


def test_code_scan_resolves_code128_with_ocr_profile_present() -> None:
    strategy = _strategy(_FakeScanner("CODE128", "XYZ|3", CodeType.BARCODE))
    result = strategy.process(_context(profile_aware=True), _asset())
    assert result.status is ImageResultStatus.RESOLVED_INTERNAL
    assert result.internal_code == "XYZ"
    assert result.quantity == 3.0


def test_ocr_exact_length_does_not_apply_to_code_scan() -> None:
    """Incident a9472e04: OCR exact_length=7 must not reject 11-digit QR/CODE128."""
    cfg = default_extraction_configuration().to_public_dict()
    code_rules = dict(cfg.get("validation_rules", {}).get("code") or {})
    code_rules["exact_length"] = 7
    cfg = {
        **cfg,
        "validation_rules": {
            **dict(cfg.get("validation_rules") or {}),
            "code": code_rules,
        },
    }
    strategy = _strategy(_FakeScanner("QRCODE", "22242925205|100000", CodeType.QR))
    result = strategy.process(_context(profile_aware=True, configuration=cfg), _asset())
    assert result.status is ImageResultStatus.RESOLVED_INTERNAL
    assert result.internal_code == "22242925205"
    assert int(result.quantity) == 100000
    assert result.error_code is None
    assert (result.evidence or {}).get("profile_validation_bypassed_for_code_scan") is not True
