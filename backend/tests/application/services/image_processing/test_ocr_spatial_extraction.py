"""Unit tests for Phase 4 OCR spatial "value below label" association.

Focuses on the two failure modes that plain line-index adjacency (``idx + 1``) cannot tell
apart without spatial context: a two-column table where the "next line" belongs to an
unrelated column, and a next line that is itself a label rather than a value.
"""

from __future__ import annotations

from src.application.ports.internal_label_reader import InternalOcrReadResult, OcrTextBlock
from src.application.services.image_processing.ocr_field_extractor import (
    OcrFieldExtractor,
    _horizontal_overlap,
)


def _block(
    text: str,
    *,
    block_num: int,
    line_num: int,
    left: int,
    top: int = 10,
    width: int = 60,
    height: int = 20,
    confidence: float | None = 90.0,
) -> OcrTextBlock:
    return OcrTextBlock(
        text=text,
        confidence=confidence,
        left=left,
        top=top,
        width=width,
        height=height,
        line_num=line_num,
        block_num=block_num,
    )


def _read(blocks: list[OcrTextBlock]) -> InternalOcrReadResult:
    full_text = "\n".join(b.text for b in blocks)
    return InternalOcrReadResult(
        full_text=full_text,
        text_blocks=tuple(blocks),
        confidence=90.0,
        orientation=0,
        engine_name="fake",
        engine_version="0",
        duration_ms=1,
    )


def test_below_label_accepts_aligned_value_in_same_column() -> None:
    blocks = [
        _block("CODIGO", block_num=1, line_num=0, left=10, width=60),
        _block("SKU42", block_num=1, line_num=1, left=15, width=50),
    ]
    extraction = OcrFieldExtractor().extract(_read(blocks))
    assert any(
        c.value == "SKU42" and c.rule == "below_label" for c in extraction.internal_code_candidates
    )


def test_below_label_rejects_cross_column_value_in_two_column_table() -> None:
    # Two-column table: Tesseract commonly assigns a distinct block_num per column. The label
    # is the last line of its (left) column block, so plain idx+1 adjacency would otherwise
    # jump straight into the first line of the unrelated (right) column block.
    blocks = [
        _block("CODIGO", block_num=1, line_num=0, left=10, width=60),
        _block("450", block_num=2, line_num=0, left=10, width=30),
    ]
    extraction = OcrFieldExtractor().extract(_read(blocks))
    assert not any(c.rule == "below_label" for c in extraction.internal_code_candidates)


def test_below_label_requires_horizontal_overlap_within_same_block() -> None:
    # Same OCR block, but the two lines sit in visually unrelated columns (far apart on the
    # x-axis) — must not be treated as label/value pair even though block_num matches.
    blocks = [
        _block("CODIGO", block_num=1, line_num=0, left=10, width=60),
        _block("999999999999", block_num=1, line_num=1, left=300, width=60),
    ]
    extraction = OcrFieldExtractor().extract(_read(blocks))
    labeled = [c for c in extraction.internal_code_candidates if c.rule == "below_label"]
    assert not labeled
    # The bare-EAN scan is a separate rule; it may still legitimately pick up the token.
    assert all(c.rule != "below_label" for c in extraction.ean_candidates)


def test_below_label_skips_when_next_line_is_itself_a_known_alias() -> None:
    # "CANTIDAD" directly below "CODIGO" is a second label (e.g. two stacked headers), not a
    # code value — must not be adopted as CODIGO's answer.
    blocks = [
        _block("CODIGO", block_num=1, line_num=0, left=10, width=60),
        _block("CANTIDAD", block_num=1, line_num=1, left=10, width=60),
    ]
    extraction = OcrFieldExtractor().extract(_read(blocks))
    assert not any(c.rule == "below_label" for c in extraction.internal_code_candidates)
    assert not any(c.rule == "below_label" for c in extraction.quantity_candidates)


def test_below_label_prefers_same_block_num_over_line_adjacency() -> None:
    # Article alias label followed (in raw line order) by a value that actually lives in a
    # different block/column — must be rejected in favor of no association at all, rather
    # than silently pairing across the column boundary.
    blocks = [
        _block("ARTICULO", block_num=1, line_num=0, left=10, width=60),
        _block("XYZ99", block_num=2, line_num=0, left=15, width=50),
    ]
    extraction = OcrFieldExtractor().extract(_read(blocks))
    assert not any(c.rule == "below_label" for c in extraction.article_candidates)
    assert not any(c.rule == "below_label" for c in extraction.internal_code_candidates)


def test_horizontal_overlap_true_when_either_region_missing() -> None:
    assert _horizontal_overlap(None, (0, 0, 10, 10)) is True
    assert _horizontal_overlap((0, 0, 10, 10), None) is True


def test_horizontal_overlap_true_for_overlapping_intervals() -> None:
    assert _horizontal_overlap((10, 0, 60, 20), (15, 0, 50, 20)) is True


def test_horizontal_overlap_true_for_small_gap_within_half_parent_width() -> None:
    # No actual [left, left+width] overlap (a ends at 70, b starts at 75 → gap of 5), but the
    # gap is well within half of a's width (30) so this still counts as spatially aligned.
    assert _horizontal_overlap((10, 0, 60, 20), (75, 0, 10, 20)) is True


def test_horizontal_overlap_false_for_distant_regions() -> None:
    assert _horizontal_overlap((10, 0, 60, 20), (300, 0, 60, 20)) is False
