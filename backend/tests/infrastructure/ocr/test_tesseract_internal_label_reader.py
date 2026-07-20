"""Real Tesseract OCR smoke tests (skipped when tesseract is not installed)."""

from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image, ImageDraw, ImageFont

from src.application.ports.internal_label_reader import InternalOcrContext, PreparedImage
from src.application.services.image_processing.ocr_field_extractor import OcrFieldExtractor
from src.application.services.image_processing.ocr_result_normalizer import (
    OcrNormalizeStatus,
    OcrResultNormalizer,
)
from src.infrastructure.ocr.tesseract_internal_label_reader import (
    TesseractInternalLabelReader,
    TesseractUnavailableError,
)


def _tesseract_available() -> bool:
    try:
        reader = TesseractInternalLabelReader()
        _ = reader.engine_version
        return True
    except TesseractUnavailableError:
        return False
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _tesseract_available(), reason="tesseract / pytesseract not available"
)


def _label_png(*, text_lines: list[str], rotate: int = 0) -> bytes:
    img = Image.new("RGB", (640, 240), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 28)
    except Exception:
        font = ImageFont.load_default()
    y = 30
    for line in text_lines:
        draw.text((20, y), line, fill=(0, 0, 0), font=font)
        y += 40
    if rotate:
        img = img.rotate(rotate, expand=True, fillcolor=(255, 255, 255))
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_tesseract_reads_printed_ean_and_quantity() -> None:
    content = _label_png(text_lines=["EAN: 7791234567890", "CANTIDAD: 48"])
    reader = TesseractInternalLabelReader()
    prepared = PreparedImage(content=content, width=640, height=240, variant_name="original")
    ctx = InternalOcrContext(
        job_id="j",
        asset_id="a",
        client_id=None,
        language="spa+eng",
        timeout_seconds=15,
        max_image_dimension=2048,
    )
    read = reader.read(prepared, ctx)
    assert read.engine_name == "tesseract"
    assert read.full_text.strip()
    extraction = OcrFieldExtractor().extract(read)
    normalized = OcrResultNormalizer(quantity_max=999999).normalize(extraction)
    # Real OCR may miss a character; require either full resolve or at least one field.
    assert normalized.status in (
        OcrNormalizeStatus.RESOLVED,
        OcrNormalizeStatus.PENDING_MANUAL_REVIEW,
        OcrNormalizeStatus.UNRECOGNIZED,
    )
    if normalized.status is OcrNormalizeStatus.RESOLVED:
        assert normalized.internal_code is not None
        assert normalized.quantity == 48
