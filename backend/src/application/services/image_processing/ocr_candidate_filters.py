"""Typed OCR candidate rejection rules (length, charset, packaging measurements).

Rejects are explicit reason codes — never silent drops.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import Enum

from src.domain.client_supplier.extraction_profile import CodeValidationRules


class OcrCandidateRejectReason(str, Enum):
    CODE_LENGTH_TOO_SHORT = "CODE_LENGTH_TOO_SHORT"
    CODE_LENGTH_TOO_LONG = "CODE_LENGTH_TOO_LONG"
    CODE_LENGTH_NOT_EXACT = "CODE_LENGTH_NOT_EXACT"
    CODE_INVALID_CHARSET = "CODE_INVALID_CHARSET"
    CODE_FORBIDDEN_CONTEXT = "CODE_FORBIDDEN_CONTEXT"
    CODE_MEASUREMENT_PATTERN = "CODE_MEASUREMENT_PATTERN"
    CODE_UNIT_SUFFIX = "CODE_UNIT_SUFFIX"


# Safe typed patterns (no user-supplied regex).
_MEASUREMENT_DIM = re.compile(
    r"^\d{1,4}\s*[xX×]\s*\d{1,4}(?:\s*[xX×]\s*\d{1,4})?$",
    re.UNICODE,
)
_UNIT_SUFFIX = re.compile(
    r"^\d+[.,]?\d*\s*(mm|cm|m|m2|m²|kg|g|gr|lb|oz|un|uds?|pcs?|%)\b",
    re.IGNORECASE | re.UNICODE,
)
_DECIMAL_MEASURE = re.compile(r"^\d+[.,]\d+$")


@dataclass(frozen=True)
class CandidateFilterDecision:
    accepted: bool
    reason_code: str | None = None
    rule: str | None = None


def _fold(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text or "")
    return "".join(ch for ch in nfkd if not unicodedata.combining(ch)).casefold().strip()


def looks_like_measurement(value: str, *, neighbor_text: str | None = None) -> str | None:
    """Return a reject reason if value looks like packaging measurement / unit text."""
    raw = (value or "").strip()
    if not raw:
        return None
    compact = re.sub(r"\s+", "", raw)
    if _MEASUREMENT_DIM.match(compact) or _MEASUREMENT_DIM.match(raw):
        return OcrCandidateRejectReason.CODE_MEASUREMENT_PATTERN
    if _UNIT_SUFFIX.match(raw):
        return OcrCandidateRejectReason.CODE_UNIT_SUFFIX
    if _DECIMAL_MEASURE.match(raw) and any(u in _fold(raw) for u in ("m", "kg", "mm", "cm")):
        return OcrCandidateRejectReason.CODE_UNIT_SUFFIX
    neighbor = _fold(neighbor_text or "")
    if neighbor:
        if any(
            token in neighbor
            for token in ("mm", "cm", "kg", "m2", "m²", "medida", "dimension", "peso")
        ):
            # Short numeric near measurement context (e.g. "600" near "mm").
            if raw.isdigit() and len(raw) <= 4:
                return OcrCandidateRejectReason.CODE_FORBIDDEN_CONTEXT
        if "inventario general" in neighbor and raw.isdigit() and len(raw) <= 3:
            return OcrCandidateRejectReason.CODE_FORBIDDEN_CONTEXT
    return None


def filter_internal_code_candidate(
    value: str,
    *,
    rules: CodeValidationRules,
    neighbor_text: str | None = None,
) -> CandidateFilterDecision:
    text = (value or "").strip()
    if not rules.allow_spaces:
        text = text.replace(" ", "")

    if rules.reject_measurement_patterns:
        measure_reason = looks_like_measurement(value, neighbor_text=neighbor_text)
        if measure_reason:
            return CandidateFilterDecision(
                accepted=False,
                reason_code=measure_reason,
                rule="reject_measurement_patterns",
            )

    length = len(text)
    if rules.exact_length is not None:
        if length != int(rules.exact_length):
            return CandidateFilterDecision(
                accepted=False,
                reason_code=OcrCandidateRejectReason.CODE_LENGTH_NOT_EXACT,
                rule="exact_length",
            )
    else:
        if length < int(rules.min_length):
            return CandidateFilterDecision(
                accepted=False,
                reason_code=OcrCandidateRejectReason.CODE_LENGTH_TOO_SHORT,
                rule="min_length",
            )
        if length > int(rules.max_length):
            return CandidateFilterDecision(
                accepted=False,
                reason_code=OcrCandidateRejectReason.CODE_LENGTH_TOO_LONG,
                rule="max_length",
            )

    for ch in text:
        if ch.isalpha() and not rules.allow_letters:
            return CandidateFilterDecision(
                accepted=False,
                reason_code=OcrCandidateRejectReason.CODE_INVALID_CHARSET,
                rule="allow_letters",
            )
        if ch.isdigit() and not rules.allow_digits:
            return CandidateFilterDecision(
                accepted=False,
                reason_code=OcrCandidateRejectReason.CODE_INVALID_CHARSET,
                rule="allow_digits",
            )
        if ch == "-" and not rules.allow_hyphen:
            return CandidateFilterDecision(
                accepted=False,
                reason_code=OcrCandidateRejectReason.CODE_INVALID_CHARSET,
                rule="allow_hyphen",
            )
        if ch == "/" and not rules.allow_slash:
            return CandidateFilterDecision(
                accepted=False,
                reason_code=OcrCandidateRejectReason.CODE_INVALID_CHARSET,
                rule="allow_slash",
            )
        if ch not in "-/" and not ch.isalnum() and ch != " ":
            return CandidateFilterDecision(
                accepted=False,
                reason_code=OcrCandidateRejectReason.CODE_INVALID_CHARSET,
                rule="charset",
            )

    return CandidateFilterDecision(accepted=True)


__all__ = [
    "CandidateFilterDecision",
    "OcrCandidateRejectReason",
    "filter_internal_code_candidate",
    "looks_like_measurement",
]
