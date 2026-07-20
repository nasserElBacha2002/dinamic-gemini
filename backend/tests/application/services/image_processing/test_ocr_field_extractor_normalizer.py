"""Unit tests for Phase 4 OCR field extraction + normalization."""

from __future__ import annotations

from src.application.ports.internal_label_reader import InternalOcrReadResult, OcrTextBlock
from src.application.services.image_processing.ocr_field_extractor import OcrFieldExtractor
from src.application.services.image_processing.ocr_result_normalizer import (
    OcrClientFieldRules,
    OcrNormalizeStatus,
    OcrResultNormalizer,
)


def _read(full_text: str, blocks: list[OcrTextBlock] | None = None) -> InternalOcrReadResult:
    return InternalOcrReadResult(
        full_text=full_text,
        text_blocks=tuple(blocks or ()),
        confidence=90.0,
        orientation=0,
        engine_name="fake",
        engine_version="0",
        duration_ms=1,
    )


def test_extract_labeled_ean_and_quantity() -> None:
    read = _read("EAN: 7791234567890\nCANTIDAD: 48")
    extraction = OcrFieldExtractor().extract(read)
    assert extraction.ean_candidates
    assert extraction.ean_candidates[0].value == "7791234567890"
    assert extraction.quantity_candidates
    assert extraction.quantity_candidates[0].value == "48"


def test_normalize_prefers_ean_over_articulo() -> None:
    read = _read("EAN: 7791234567890\nARTICULO: ABC99\nCANTIDAD: 12")
    extraction = OcrFieldExtractor().extract(read)
    normalized = OcrResultNormalizer(
        quantity_max=9999,
        client_rules=OcrClientFieldRules(prefer_ean_as_internal_code=True),
    ).normalize(extraction)
    assert normalized.status is OcrNormalizeStatus.RESOLVED
    assert normalized.internal_code == "7791234567890"
    assert normalized.quantity == 12
    assert normalized.additional_fields.get("articulo") == "ABC99"


def test_normalize_rejects_zero_quantity() -> None:
    read = _read("CODIGO: SKU1\nCANTIDAD: 0")
    extraction = OcrFieldExtractor().extract(read)
    normalized = OcrResultNormalizer(quantity_max=9999).normalize(extraction)
    assert normalized.status is not OcrNormalizeStatus.RESOLVED
    assert normalized.quantity is None


def test_normalize_ambiguous_quantity() -> None:
    read = _read("CODIGO: SKU1\nCANTIDAD: 10\nCANTIDAD: 20")
    extraction = OcrFieldExtractor().extract(read)
    normalized = OcrResultNormalizer(quantity_max=9999).normalize(extraction)
    assert normalized.status is OcrNormalizeStatus.AMBIGUOUS
    assert "AMBIGUOUS_QUANTITY" in normalized.warnings


def test_normalize_missing_code() -> None:
    read = _read("CANTIDAD: 5")
    extraction = OcrFieldExtractor().extract(read)
    normalized = OcrResultNormalizer(quantity_max=9999).normalize(extraction)
    assert normalized.status is OcrNormalizeStatus.PENDING_MANUAL_REVIEW
    assert "NO_INTERNAL_CODE" in normalized.validation_errors


def test_normalize_unrecognized_when_empty() -> None:
    read = _read("sin etiqueta util")
    extraction = OcrFieldExtractor().extract(read)
    normalized = OcrResultNormalizer(quantity_max=9999).normalize(extraction)
    assert normalized.status is OcrNormalizeStatus.UNRECOGNIZED
