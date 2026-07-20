"""Unit tests for Phase 4 InternalOcrProcessingStrategy confidence gating (LOW_OCR_CONFIDENCE)."""

from __future__ import annotations

from datetime import datetime, timezone

from src.application.ports.internal_label_reader import (
    InternalOcrContext,
    InternalOcrReadResult,
    OcrTextBlock,
    PreparedImage,
)
from src.application.services.image_processing.internal_ocr_processing_strategy import (
    InternalOcrConfig,
    InternalOcrProcessingStrategy,
)
from src.application.services.image_processing.ocr_field_extractor import OcrFieldExtractor
from src.application.services.image_processing.ocr_image_preprocessor import (
    OcrImagePreprocessor,
    OcrPreprocessConfig,
)
from src.application.services.image_processing.ocr_result_normalizer import OcrResultNormalizer
from src.domain.aisle_identification.modes import (
    AisleIdentificationExecutionStrategy,
    AisleIdentificationMode,
)
from src.domain.assets.entities import SourceAsset, SourceAssetType
from src.domain.image_processing.contracts import (
    ExecutionScope,
    ImageProcessingContext,
    ImageResultStatus,
)


class _FakeReader:
    engine_name = "fake"
    engine_version = "1"

    def __init__(self, full_text: str, *, confidence: float | None) -> None:
        self._full_text = full_text
        self._confidence = confidence

    def read(self, image: PreparedImage, context: InternalOcrContext) -> InternalOcrReadResult:
        return InternalOcrReadResult(
            full_text=self._full_text,
            text_blocks=(OcrTextBlock(text=self._full_text, confidence=self._confidence),),
            confidence=self._confidence,
            orientation=0,
            engine_name=self.engine_name,
            engine_version=self.engine_version,
            duration_ms=5,
        )


class _BytesReader:
    def __init__(self, content: bytes) -> None:
        self._content = content

    def read_image_bytes(self, asset: SourceAsset) -> bytes:
        return self._content


def _png_bytes() -> bytes:
    from io import BytesIO

    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", (200, 80), color=(255, 255, 255)).save(buf, format="PNG")
    return buf.getvalue()


def _asset() -> SourceAsset:
    return SourceAsset(
        id="asset-1",
        aisle_id="aisle-1",
        type=SourceAssetType.PHOTO,
        original_filename="asset-1.jpg",
        storage_path="/asset-1.jpg",
        mime_type="image/jpeg",
        uploaded_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def _context() -> ImageProcessingContext:
    return ImageProcessingContext(
        job_id="job-1",
        asset_id="asset-1",
        aisle_id="aisle-1",
        inventory_id="inv-1",
        client_id=None,
        identification_mode=AisleIdentificationMode.INTERNAL_OCR,
        execution_strategy=AisleIdentificationExecutionStrategy.INTERNAL_OCR,
        configuration_snapshot_version=1,
        provider_name=None,
        model_name=None,
        prompt_key=None,
        prompt_version=None,
        attempt_number=1,
        execution_scope=ExecutionScope.SINGLE_ASSET,
    )


def _strategy(reader, *, min_aggregate_confidence: float | None) -> InternalOcrProcessingStrategy:
    return InternalOcrProcessingStrategy(
        reader=reader,
        content_reader=_BytesReader(_png_bytes()),
        preprocessor=OcrImagePreprocessor(
            OcrPreprocessConfig(max_variants=1, enable_adaptive_threshold=False)
        ),
        extractor=OcrFieldExtractor(),
        normalizer=OcrResultNormalizer(quantity_max=9999),
        config=InternalOcrConfig(
            quantity_max=9999,
            max_variants=1,
            timeout_seconds=30,
            min_aggregate_confidence=min_aggregate_confidence,
        ),
    )


_LABEL_TEXT = "CODIGO: SKU42\nCANTIDAD: 7"


def test_confidence_disabled_resolves_regardless_of_low_confidence() -> None:
    strategy = _strategy(_FakeReader(_LABEL_TEXT, confidence=10.0), min_aggregate_confidence=None)
    result = strategy.process(_context(), _asset())
    assert result.status is ImageResultStatus.RESOLVED_INTERNAL
    assert result.internal_code == "SKU42"


def test_confidence_at_or_above_threshold_resolves() -> None:
    strategy = _strategy(
        _FakeReader(_LABEL_TEXT, confidence=80.0), min_aggregate_confidence=75.0
    )
    result = strategy.process(_context(), _asset())
    assert result.status is ImageResultStatus.RESOLVED_INTERNAL
    assert result.internal_code == "SKU42"
    assert result.quantity == 7.0


def test_confidence_below_threshold_demotes_to_manual_review_not_resolved() -> None:
    strategy = _strategy(
        _FakeReader(_LABEL_TEXT, confidence=40.0), min_aggregate_confidence=75.0
    )
    result = strategy.process(_context(), _asset())

    assert result.status is ImageResultStatus.PENDING_MANUAL_REVIEW
    assert result.error_code == "LOW_OCR_CONFIDENCE"
    assert "LOW_OCR_CONFIDENCE" in result.validation_errors
    assert "LOW_OCR_CONFIDENCE" in result.warnings
    # The extracted fields are still surfaced for the reviewer, just not auto-accepted.
    assert result.internal_code == "SKU42"
    assert result.quantity == 7.0

    evidence = result.evidence
    assert evidence is not None
    assert evidence["confidence"] == 40.0
    assert evidence["confidence_threshold"] == 75.0
    assert evidence["preprocessing_variant"]
    assert evidence["selected_variant"]
    assert evidence["engine_name"] == "fake"
    assert evidence["selected_code_rule"] is not None
    assert evidence["selected_qty_rule"] is not None


def test_confidence_missing_with_threshold_configured_fails_closed() -> None:
    strategy = _strategy(_FakeReader(_LABEL_TEXT, confidence=None), min_aggregate_confidence=75.0)
    result = strategy.process(_context(), _asset())

    assert result.status is ImageResultStatus.PENDING_MANUAL_REVIEW
    assert result.error_code == "LOW_OCR_CONFIDENCE"
    assert "LOW_OCR_CONFIDENCE" in result.validation_errors


def test_low_confidence_does_not_mutate_or_leak_as_resolved_metric() -> None:
    strategy = _strategy(
        _FakeReader(_LABEL_TEXT, confidence=10.0), min_aggregate_confidence=75.0
    )
    result = strategy.process(_context(), _asset())

    assert result.status is not ImageResultStatus.RESOLVED_INTERNAL
    snapshot = strategy.metrics.snapshot()
    assert snapshot.get("ocr_resolved_total", 0) == 0
    assert snapshot.get("ocr_low_confidence_total", 0) == 1
    assert snapshot.get("ocr_manual_review_total", 0) == 1
