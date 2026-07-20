"""Unit tests for OCR token normalizer, anchor matcher, and numeric candidates."""

from __future__ import annotations

from src.application.ports.internal_label_reader import InternalOcrReadResult, OcrTextBlock
from src.application.services.image_processing.field_candidate_set import (
    FieldCandidateSet,
    apply_profile_validation,
)
from src.application.services.image_processing.ocr_anchor_matcher import (
    AnchorMatchMode,
    OcrAnchorMatcher,
)
from src.application.services.image_processing.ocr_field_extractor import OcrFieldExtractor
from src.application.services.image_processing.ocr_token_normalizer import (
    OcrTokenNormalizer,
    fold_ocr_text,
)
from src.application.services.image_processing.profile_aware_processing_result_validator import (
    FieldCandidate,
)
from src.domain.client_supplier.extraction_profile import (
    inventory_seven_digit_internal_code_template,
)
from src.domain.image_processing.contracts import ImageResultStatus


def test_fold_strips_accents_and_ocr_confusion() -> None:
    assert fold_ocr_text("CÓDIGO INTERNO") == "codigo interno"
    assert fold_ocr_text("CODIGO INTEMO") == "codigo interno"


def test_anchor_exact_and_split_tokens() -> None:
    matcher = OcrAnchorMatcher(mode=AnchorMatchMode.FUZZY)
    normalizer = OcrTokenNormalizer()
    tokens = normalizer.normalize_blocks(
        (
            OcrTextBlock(text="CODIGO", confidence=90, left=10, top=10, width=40, height=12, block_num=1, line_num=1),
            OcrTextBlock(text="INTEMO", confidence=88, left=55, top=10, width=50, height=12, block_num=1, line_num=1),
        )
    )
    hits = matcher.match_anchors(
        configured_anchors=("CÓDIGO INTERNO",),
        tokens=tokens,
    )
    assert hits
    assert hits[0].similarity >= 0.82


def test_anchor_fuzzy_below_threshold_rejected() -> None:
    matcher = OcrAnchorMatcher(mode=AnchorMatchMode.FUZZY, similarity_threshold=0.95)
    normalizer = OcrTokenNormalizer()
    tokens = normalizer.normalize_blocks(
        (OcrTextBlock(text="xyzabc", confidence=50, left=0, top=0, width=10, height=10),)
    )
    hits = matcher.match_anchors(configured_anchors=("CODIGO INTERNO",), tokens=tokens)
    assert hits == []


def test_extractor_numeric_seven_digit_without_anchor() -> None:
    cfg = inventory_seven_digit_internal_code_template()
    read = InternalOcrReadResult(
        full_text="1428706\n60x60\n600 mm\n26",
        text_blocks=(
            OcrTextBlock(text="1428706", confidence=90, left=20, top=40, width=80, height=16, block_num=1, line_num=1),
            OcrTextBlock(text="60x60", confidence=80, left=20, top=70, width=40, height=12, block_num=1, line_num=2),
            OcrTextBlock(text="600", confidence=80, left=20, top=90, width=30, height=12, block_num=1, line_num=3),
            OcrTextBlock(text="mm", confidence=80, left=55, top=90, width=20, height=12, block_num=1, line_num=3),
            OcrTextBlock(text="26", confidence=80, left=20, top=110, width=20, height=12, block_num=1, line_num=4),
        ),
        confidence=85.0,
        orientation=0,
        engine_name="fake",
        engine_version="1",
        duration_ms=5,
    )
    extraction = OcrFieldExtractor().extract(read, configuration=cfg)
    values = {c.value for c in extraction.internal_code_candidates}
    assert "1428706" in values
    assert "60x60" not in values
    assert "26" not in values
    assert extraction.stats.get("raw_numeric_token_count", 0) >= 1
    assert any(
        r.get("reason_code") in {"CODE_MEASUREMENT_PATTERN", "CODE_LENGTH_NOT_EXACT", "CODE_FORBIDDEN_CONTEXT"}
        for r in extraction.rejected_candidates
    )


def test_unanchored_code_missing_qty_manual_review() -> None:
    cfg = inventory_seven_digit_internal_code_template()
    result = apply_profile_validation(
        job_id="j1",
        asset_id="a1",
        processing_mode="INTERNAL_OCR",
        resolved_by="INTERNAL_OCR",
        candidates=FieldCandidateSet(
            code_candidates=[
                FieldCandidate(
                    source_key="INTERNAL_CODE",
                    value="1428706",
                    evidence_score=0.7,
                    labeled=False,
                    extraction_method="NUMERIC_PATTERN",
                )
            ],
            quantity_candidates=[],
        ),
        configuration=cfg,
    )
    assert result.status is ImageResultStatus.PENDING_MANUAL_REVIEW
    assert result.internal_code == "1428706"
    assert result.quantity is None
    assert result.error_code == "MISSING_QUANTITY"


def test_packaging_only_unrecognized() -> None:
    cfg = inventory_seven_digit_internal_code_template()
    read = InternalOcrReadResult(
        full_text="60x60\n600 mm\n26",
        text_blocks=(
            OcrTextBlock(text="60x60", confidence=80, left=0, top=0, width=40, height=10),
            OcrTextBlock(text="600", confidence=80, left=0, top=20, width=30, height=10),
            OcrTextBlock(text="mm", confidence=80, left=35, top=20, width=20, height=10),
            OcrTextBlock(text="26", confidence=80, left=0, top=40, width=20, height=10),
        ),
        confidence=80.0,
        orientation=0,
        engine_name="fake",
        engine_version="1",
        duration_ms=3,
    )
    extraction = OcrFieldExtractor().extract(read, configuration=cfg)
    assert extraction.internal_code_candidates == []
    result = apply_profile_validation(
        job_id="j1",
        asset_id="a1",
        processing_mode="INTERNAL_OCR",
        resolved_by="INTERNAL_OCR",
        candidates=FieldCandidateSet(code_candidates=[], quantity_candidates=[]),
        configuration=cfg,
    )
    assert result.status is ImageResultStatus.UNRECOGNIZED
    assert "MISSING_INTERNAL_CODE" in (result.validation_errors or [])


def test_imperfect_anchor_codigo_intemo_with_code() -> None:
    cfg = inventory_seven_digit_internal_code_template()
    read = InternalOcrReadResult(
        full_text="CODIGO\nINTEMO\n1428706",
        text_blocks=(
            OcrTextBlock(text="CODIGO", confidence=90, left=10, top=10, width=40, height=12, block_num=1, line_num=1),
            OcrTextBlock(text="INTEMO", confidence=88, left=55, top=10, width=50, height=12, block_num=1, line_num=1),
            OcrTextBlock(text="1428706", confidence=92, left=20, top=40, width=80, height=16, block_num=1, line_num=2),
        ),
        confidence=90.0,
        orientation=0,
        engine_name="fake",
        engine_version="1",
        duration_ms=4,
    )
    extraction = OcrFieldExtractor().extract(read, configuration=cfg)
    assert any(c.value == "1428706" for c in extraction.internal_code_candidates)
    assert extraction.stats.get("matched_anchor_count", 0) >= 1
