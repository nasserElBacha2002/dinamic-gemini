"""OCR candidate origin / acceptance policy contracts."""

from __future__ import annotations

from src.application.services.image_processing.ocr_candidate_policy import (
    OcrCandidateAcceptance,
    OcrCandidateOrigin,
    classify_ocr_field_origin,
    decide_candidate_acceptance,
)
from src.application.services.image_processing.ocr_field_extractor import (
    OcrFieldCandidate,
    OcrFieldKind,
)
from src.domain.client_supplier.extraction_profile import UnanchoredCodeCandidatePolicy


def _cand(**kwargs) -> OcrFieldCandidate:
    base = dict(
        kind=OcrFieldKind.INTERNAL_CODE,
        value="1234567",
        source="numeric_pattern",
        associated_text="",
        confidence=0.9,
        region=None,
        rule="t",
        extraction_method="NUMERIC_PATTERN",
        anchor_text=None,
    )
    base.update(kwargs)
    return OcrFieldCandidate(**base)


def test_classify_origins() -> None:
    assert (
        classify_ocr_field_origin(
            _cand(extraction_method="LABELED_EXACT", anchor_text="COD", source="code_label")
        )
        is OcrCandidateOrigin.ANCHORED_EXACT
    )
    assert (
        classify_ocr_field_origin(_cand(extraction_method="LABELED_FUZZY", anchor_text="COD"))
        is OcrCandidateOrigin.ANCHORED_FUZZY
    )
    assert (
        classify_ocr_field_origin(_cand())
        is OcrCandidateOrigin.UNANCHORED_PATTERN
    )
    assert (
        classify_ocr_field_origin(_cand(extraction_method="BARCODE", source="barcode"))
        is OcrCandidateOrigin.BARCODE
    )


def test_unanchored_manual_review_not_auto() -> None:
    decision = decide_candidate_acceptance(
        OcrCandidateOrigin.UNANCHORED_PATTERN,
        unanchored_policy=UnanchoredCodeCandidatePolicy.ALLOW_FOR_MANUAL_REVIEW,
    )
    assert decision is OcrCandidateAcceptance.MANUAL_REVIEW
    assert decision is not OcrCandidateAcceptance.AUTO_ACCEPT
