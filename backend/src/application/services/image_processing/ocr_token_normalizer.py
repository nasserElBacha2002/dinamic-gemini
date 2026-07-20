"""Normalize OCR tokens for alias / anchor matching without mutating persisted values."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from src.application.ports.internal_label_reader import OcrTextBlock

# Common OCR confusions on Spanish inventory anchors (limited, deterministic).
_OCR_CONFUSIONS = (
    ("intemo", "interno"),
    ("intern0", "interno"),
    ("codlgo", "codigo"),
    ("c0digo", "codigo"),
    ("codlgo", "codigo"),
    ("cantldad", "cantidad"),
    ("cantldad", "cantidad"),
)


@dataclass(frozen=True)
class NormalizedOcrToken:
    original_text: str
    normalized_text: str
    confidence: float | None
    bounding_box: tuple[int, int, int, int] | None
    line_num: int | None
    block_num: int | None
    word_num: int | None = None


def fold_ocr_text(text: str) -> str:
    """Lowercase, strip accents, collapse whitespace, strip light punctuation."""
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFKD", text)
    without_marks = "".join(ch for ch in nfkd if not unicodedata.combining(ch))
    collapsed = re.sub(r"\s+", " ", without_marks.strip())
    collapsed = re.sub(r"[^\w\s./\-]", "", collapsed, flags=re.UNICODE)
    folded = collapsed.casefold().strip()
    for bad, good in _OCR_CONFUSIONS:
        folded = folded.replace(bad, good)
    return folded


def _block_bbox(block: OcrTextBlock) -> tuple[int, int, int, int] | None:
    if block.left is None or block.top is None or block.width is None or block.height is None:
        return None
    return (int(block.left), int(block.top), int(block.width), int(block.height))


class OcrTokenNormalizer:
    """Convert OCR text blocks into normalized tokens suitable for matching."""

    def normalize_text(self, text: str) -> str:
        return fold_ocr_text(text)

    def normalize_block(self, block: OcrTextBlock) -> NormalizedOcrToken | None:
        original = (block.text or "").strip()
        if not original:
            return None
        return NormalizedOcrToken(
            original_text=original,
            normalized_text=fold_ocr_text(original),
            confidence=block.confidence,
            bounding_box=_block_bbox(block),
            line_num=block.line_num,
            block_num=block.block_num,
            word_num=getattr(block, "word_num", None),
        )

    def normalize_blocks(
        self, blocks: tuple[OcrTextBlock, ...] | list[OcrTextBlock]
    ) -> list[NormalizedOcrToken]:
        out: list[NormalizedOcrToken] = []
        for block in blocks:
            token = self.normalize_block(block)
            if token is not None:
                out.append(token)
        return out

    def split_line_tokens(self, text: str) -> list[str]:
        return [t for t in re.split(r"\s+", (text or "").strip()) if t]


__all__ = [
    "NormalizedOcrToken",
    "OcrTokenNormalizer",
    "fold_ocr_text",
]
