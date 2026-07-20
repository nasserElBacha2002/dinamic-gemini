"""Fuzzy / compositional OCR anchor matching for inventory labels."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from src.application.services.image_processing.ocr_token_normalizer import (
    NormalizedOcrToken,
    fold_ocr_text,
)


class AnchorMatchMode(str, Enum):
    EXACT_ONLY = "EXACT_ONLY"
    NORMALIZED = "NORMALIZED"
    FUZZY = "FUZZY"


@dataclass(frozen=True)
class AnchorMatch:
    configured_anchor: str
    matched_text: str
    mode: str
    similarity: float
    bounding_box: tuple[int, int, int, int] | None
    line_num: int | None
    block_num: int | None
    token_count: int = 1


def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        cur = [i]
        for j, cb in enumerate(b, start=1):
            ins = cur[j - 1] + 1
            delete = prev[j] + 1
            sub = prev[j - 1] + (0 if ca == cb else 1)
            cur.append(min(ins, delete, sub))
        prev = cur
    return prev[-1]


def similarity_ratio(a: str, b: str) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    dist = _levenshtein(a, b)
    return 1.0 - (dist / max(len(a), len(b)))


def _merge_bbox(
    boxes: list[tuple[int, int, int, int] | None],
) -> tuple[int, int, int, int] | None:
    valid = [b for b in boxes if b is not None]
    if not valid:
        return None
    left = min(b[0] for b in valid)
    top = min(b[1] for b in valid)
    right = max(b[0] + b[2] for b in valid)
    bottom = max(b[1] + b[3] for b in valid)
    return (left, top, right - left, bottom - top)


class OcrAnchorMatcher:
    """Match configured anchors against OCR tokens (exact / composed / fuzzy)."""

    def __init__(
        self,
        *,
        mode: AnchorMatchMode = AnchorMatchMode.FUZZY,
        similarity_threshold: float = 0.82,
        max_compose_tokens: int = 4,
        min_anchor_chars_for_fuzzy: int = 6,
    ) -> None:
        self._mode = mode
        self._threshold = float(similarity_threshold)
        self._max_compose = max(1, int(max_compose_tokens))
        self._min_fuzzy_chars = int(min_anchor_chars_for_fuzzy)

    def match_anchors(
        self,
        *,
        configured_anchors: tuple[str, ...] | list[str],
        tokens: list[NormalizedOcrToken],
        line_texts: list[tuple[str, NormalizedOcrToken | None]] | None = None,
    ) -> list[AnchorMatch]:
        anchors = [a for a in configured_anchors if (a or "").strip()]
        if not anchors or not tokens:
            return []
        matches: list[AnchorMatch] = []
        seen: set[tuple[str, str]] = set()

        # 1) Full line / token exact+normalized.
        candidates: list[tuple[str, NormalizedOcrToken | None, tuple[int, int, int, int] | None]] = []
        for tok in tokens:
            candidates.append((tok.normalized_text, tok, tok.bounding_box))
        if line_texts:
            for text, tok in line_texts:
                candidates.append((fold_ocr_text(text), tok, tok.bounding_box if tok else None))

        for anchor in anchors:
            target = fold_ocr_text(anchor)
            if not target:
                continue
            for text, tok, bbox in candidates:
                hit = self._score_text(target, text)
                if hit is None:
                    continue
                key = (target, hit[0])
                if key in seen:
                    continue
                seen.add(key)
                matches.append(
                    AnchorMatch(
                        configured_anchor=anchor,
                        matched_text=hit[0],
                        mode=hit[1],
                        similarity=hit[2],
                        bounding_box=bbox,
                        line_num=tok.line_num if tok else None,
                        block_num=tok.block_num if tok else None,
                        token_count=1,
                    )
                )

        # 2) Compose adjacent same-line tokens into multi-word anchors.
        by_line: dict[tuple[int | None, int | None], list[NormalizedOcrToken]] = {}
        for tok in tokens:
            by_line.setdefault((tok.block_num, tok.line_num), []).append(tok)
        for group in by_line.values():
            ordered = sorted(
                group,
                key=lambda t: (t.bounding_box[0] if t.bounding_box else 0),
            )
            for i in range(len(ordered)):
                for width in range(2, min(self._max_compose, len(ordered) - i) + 1):
                    chunk = ordered[i : i + width]
                    composed = " ".join(t.normalized_text for t in chunk)
                    bbox = _merge_bbox([t.bounding_box for t in chunk])
                    for anchor in anchors:
                        target = fold_ocr_text(anchor)
                        if not target or " " not in target:
                            continue
                        hit = self._score_text(target, composed)
                        if hit is None:
                            continue
                        key = (target, hit[0])
                        if key in seen:
                            continue
                        seen.add(key)
                        matches.append(
                            AnchorMatch(
                                configured_anchor=anchor,
                                matched_text=hit[0],
                                mode=hit[1],
                                similarity=hit[2],
                                bounding_box=bbox,
                                line_num=chunk[0].line_num,
                                block_num=chunk[0].block_num,
                                token_count=width,
                            )
                        )

        # Prefer higher similarity per configured anchor.
        best: dict[str, AnchorMatch] = {}
        for m in matches:
            key = fold_ocr_text(m.configured_anchor)
            prev = best.get(key)
            if prev is None or m.similarity > prev.similarity:
                best[key] = m
        return list(best.values())

    def _score_text(
        self, target: str, text: str
    ) -> tuple[str, str, float] | None:
        if not text:
            return None
        if self._mode is AnchorMatchMode.EXACT_ONLY:
            if text == target:
                return text, "EXACT", 1.0
            return None
        if text == target:
            return text, "NORMALIZED", 1.0
        # Containment only when lengths are close (avoid "sku" ⊂ "sku42").
        if target in text or text in target:
            shorter, longer = (text, target) if len(text) <= len(target) else (target, text)
            if len(shorter) >= 4 and (len(shorter) / max(1, len(longer))) >= 0.75:
                return text, "NORMALIZED", 0.95
        if self._mode is AnchorMatchMode.NORMALIZED:
            return None
        if len(target) < self._min_fuzzy_chars:
            return None
        ratio = similarity_ratio(target, text)
        if ratio >= self._threshold:
            return text, "FUZZY", ratio
        # Token-level: allow "codigo intemo" vs "codigo interno"
        t_parts = target.split()
        x_parts = text.split()
        if len(t_parts) == len(x_parts) and len(t_parts) >= 2:
            part_scores = [similarity_ratio(a, b) for a, b in zip(t_parts, x_parts)]
            if part_scores and min(part_scores) >= self._threshold:
                return text, "FUZZY", sum(part_scores) / len(part_scores)
        return None


__all__ = [
    "AnchorMatch",
    "AnchorMatchMode",
    "OcrAnchorMatcher",
    "similarity_ratio",
]
