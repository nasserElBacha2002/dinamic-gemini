"""Unit tests for OCR image preprocessing variants."""

from __future__ import annotations

from io import BytesIO

from PIL import Image

from src.application.services.image_processing.ocr_image_preprocessor import (
    VARIANT_GRAY_CONTRAST,
    VARIANT_ORIGINAL,
    OcrImagePreprocessor,
    OcrPreprocessConfig,
)


def _rgb_png(*, size=(120, 80)) -> bytes:
    buf = BytesIO()
    Image.new("RGB", size, color=(200, 180, 160)).save(buf, format="PNG")
    return buf.getvalue()


def test_prepare_variants_respects_max() -> None:
    prep = OcrImagePreprocessor(
        OcrPreprocessConfig(max_variants=2, enable_adaptive_threshold=True, enable_deskew=True)
    )
    variants = prep.prepare_variants(_rgb_png())
    assert len(variants) == 2
    assert variants[0].variant_name == VARIANT_ORIGINAL
    assert variants[1].variant_name == VARIANT_GRAY_CONTRAST
    assert variants[0].width <= 2048


def test_prepare_variants_downscales() -> None:
    prep = OcrImagePreprocessor(
        OcrPreprocessConfig(max_image_dimension=64, max_variants=1, enable_gray_contrast=False)
    )
    variants = prep.prepare_variants(_rgb_png(size=(400, 300)))
    assert len(variants) == 1
    assert max(variants[0].width, variants[0].height) <= 64
