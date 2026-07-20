"""Unit tests for Phase 4 InternalOcrProcessingStrategy (fake reader)."""

from __future__ import annotations

from src.application.ports.internal_label_reader import (
    InternalOcrContext,
    InternalOcrEngineTimeoutError,
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
from datetime import datetime, timezone


class _FakeReader:
    engine_name = "fake"
    engine_version = "1"

    def __init__(self, full_text: str, *, fail: Exception | None = None) -> None:
        self._full_text = full_text
        self._fail = fail

    def read(self, image: PreparedImage, context: InternalOcrContext) -> InternalOcrReadResult:
        if self._fail is not None:
            raise self._fail
        return InternalOcrReadResult(
            full_text=self._full_text,
            text_blocks=(OcrTextBlock(text=self._full_text, confidence=95.0),),
            confidence=95.0,
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


def _strategy(reader) -> InternalOcrProcessingStrategy:
    return InternalOcrProcessingStrategy(
        reader=reader,
        content_reader=_BytesReader(_png_bytes()),
        preprocessor=OcrImagePreprocessor(
            OcrPreprocessConfig(max_variants=1, enable_adaptive_threshold=False)
        ),
        extractor=OcrFieldExtractor(),
        normalizer=OcrResultNormalizer(quantity_max=9999),
        config=InternalOcrConfig(quantity_max=9999, max_variants=1, timeout_seconds=30),
    )


def test_strategy_resolves_labeled_text() -> None:
    result = _strategy(_FakeReader("CODIGO: SKU42\nCANTIDAD: 7")).process(_context(), _asset())
    assert result.status is ImageResultStatus.RESOLVED_INTERNAL
    assert result.internal_code == "SKU42"
    assert result.quantity == 7.0
    assert result.resolved_by == "INTERNAL_OCR"
    assert result.evidence is not None
    assert "full_text_sha256" in result.evidence


def test_strategy_unrecognized_without_fields() -> None:
    result = _strategy(_FakeReader("hola mundo")).process(_context(), _asset())
    assert result.status is ImageResultStatus.UNRECOGNIZED


def test_strategy_technical_on_timeout() -> None:
    result = _strategy(
        _FakeReader("", fail=InternalOcrEngineTimeoutError("timeout"))
    ).process(_context(), _asset())
    assert result.status is ImageResultStatus.FAILED_TECHNICAL
    assert result.error_code == "INTERNAL_OCR_TIMEOUT"


def test_strategy_empty_asset_technical() -> None:
    strategy = InternalOcrProcessingStrategy(
        reader=_FakeReader("CODIGO: X\nCANTIDAD: 1"),
        content_reader=_BytesReader(b""),
        preprocessor=OcrImagePreprocessor(OcrPreprocessConfig(max_variants=1)),
        extractor=OcrFieldExtractor(),
        normalizer=OcrResultNormalizer(quantity_max=9999),
        config=InternalOcrConfig(quantity_max=9999, max_variants=1),
    )
    result = strategy.process(_context(), _asset())
    assert result.status is ImageResultStatus.FAILED_TECHNICAL
    assert result.error_code == "SOURCE_ASSET_EMPTY"
