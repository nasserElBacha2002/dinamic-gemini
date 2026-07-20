"""Generate preliminary numeric / alphanumeric code candidates from OCR tokens."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from src.application.services.image_processing.ocr_candidate_filters import (
    filter_internal_code_candidate,
    looks_like_measurement,
)
from src.application.services.image_processing.ocr_token_normalizer import (
    NormalizedOcrToken,
    fold_ocr_text,
)
from src.domain.client_supplier.extraction_profile import CodeValidationRules

_NUMERIC_TOKEN = re.compile(r"^\d{1,32}$")
_ALNUM_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9\-_/]{0,63}$")
_DATEISH = re.compile(r"^\d{1,4}[-/]\d{1,2}[-/]\d{1,4}$")


@dataclass(frozen=True)
class RejectedNumericToken:
    masked_value: str
    length: int
    reason_code: str
    source: str
    confidence: float | None = None
    neighbor_text: str | None = None


@dataclass
class NumericCandidateGenerationResult:
    accepted: list[dict[str, Any]] = field(default_factory=list)
    rejected: list[RejectedNumericToken] = field(default_factory=list)
    raw_numeric_token_count: int = 0
    raw_alphanumeric_token_count: int = 0
    before_filter: int = 0
    after_filter: int = 0


def mask_value(value: str) -> str:
    text = (value or "").strip()
    if len(text) <= 3:
        return "*" * len(text)
    return text[:3] + ("*" * max(0, len(text) - 3))


class OcrNumericCandidateGenerator:
    """Profile-driven preliminary candidates from raw OCR tokens (no auto-resolve)."""

    def __init__(self, *, max_tokens: int = 64) -> None:
        self._max_tokens = max(1, int(max_tokens))

    def generate(
        self,
        tokens: list[NormalizedOcrToken],
        *,
        rules: CodeValidationRules,
        neighbor_by_index: dict[int, str] | None = None,
    ) -> NumericCandidateGenerationResult:
        out = NumericCandidateGenerationResult()
        neighbors = neighbor_by_index or {}
        considered = 0
        for idx, tok in enumerate(tokens):
            if considered >= self._max_tokens:
                break
            raw = (tok.original_text or "").strip()
            if not raw or _DATEISH.match(raw):
                continue
            compact = raw.replace(" ", "")
            is_numeric = bool(_NUMERIC_TOKEN.fullmatch(compact))
            is_alnum = bool(_ALNUM_TOKEN.fullmatch(compact))
            if is_numeric:
                out.raw_numeric_token_count += 1
            elif is_alnum:
                out.raw_alphanumeric_token_count += 1
            else:
                continue
            considered += 1
            neighbor = neighbors.get(idx) or fold_ocr_text(tok.normalized_text)
            measure = looks_like_measurement(compact, neighbor_text=neighbor)
            if measure:
                out.rejected.append(
                    RejectedNumericToken(
                        masked_value=mask_value(compact),
                        length=len(compact),
                        reason_code=str(
                            getattr(measure, "value", measure) if measure else "CODE_REJECTED"
                        ),
                        source="NUMERIC_PATTERN",
                        confidence=tok.confidence,
                        neighbor_text=neighbor[:80] if neighbor else None,
                    )
                )
                continue
            out.before_filter += 1
            decision = filter_internal_code_candidate(
                compact, rules=rules, neighbor_text=neighbor
            )
            if not decision.accepted:
                out.rejected.append(
                    RejectedNumericToken(
                        masked_value=mask_value(compact),
                        length=len(compact),
                        reason_code=str(
                            getattr(decision.reason_code, "value", decision.reason_code)
                            or "CODE_REJECTED"
                        ),
                        source="NUMERIC_PATTERN",
                        confidence=tok.confidence,
                        neighbor_text=neighbor[:80] if neighbor else None,
                    )
                )
                continue
            out.after_filter += 1
            out.accepted.append(
                {
                    "value": compact,
                    "confidence": tok.confidence,
                    "bounding_box": tok.bounding_box,
                    "line_num": tok.line_num,
                    "block_num": tok.block_num,
                    "neighbor_text": neighbor[:120] if neighbor else None,
                    "extraction_method": "NUMERIC_PATTERN",
                }
            )
        return out


__all__ = [
    "NumericCandidateGenerationResult",
    "OcrNumericCandidateGenerator",
    "RejectedNumericToken",
    "mask_value",
]
