"""Explicit OCR candidate origin and acceptance decision contracts."""

from __future__ import annotations

from enum import Enum

from src.application.services.image_processing.ocr_field_extractor import OcrFieldCandidate
from src.application.services.image_processing.profile_aware_processing_result_validator import (
    FieldCandidate,
)
from src.domain.client_supplier.extraction_profile import UnanchoredCodeCandidatePolicy


class OcrCandidateOrigin(str, Enum):
    ANCHORED_EXACT = "ANCHORED_EXACT"
    ANCHORED_FUZZY = "ANCHORED_FUZZY"
    UNANCHORED_PATTERN = "UNANCHORED_PATTERN"
    BARCODE = "BARCODE"


class OcrCandidateAcceptance(str, Enum):
    AUTO_ACCEPT = "AUTO_ACCEPT"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    REJECT = "REJECT"


def classify_ocr_field_origin(candidate: OcrFieldCandidate) -> OcrCandidateOrigin:
    method = (candidate.extraction_method or "").upper()
    source = (candidate.source or "").lower()
    if method == "BARCODE" or source in {"barcode", "code_scan"}:
        return OcrCandidateOrigin.BARCODE
    if method == "LABELED_FUZZY":
        return OcrCandidateOrigin.ANCHORED_FUZZY
    if method == "LABELED_EXACT" or bool(candidate.anchor_text):
        return OcrCandidateOrigin.ANCHORED_EXACT
    if method == "NUMERIC_PATTERN" or source == "numeric_pattern":
        return OcrCandidateOrigin.UNANCHORED_PATTERN
    return OcrCandidateOrigin.UNANCHORED_PATTERN


def classify_field_candidate_origin(candidate: FieldCandidate) -> OcrCandidateOrigin:
    method = (candidate.extraction_method or "").upper()
    if method == "BARCODE" or (candidate.barcode_format or "").strip():
        return OcrCandidateOrigin.BARCODE
    if method == "LABELED_FUZZY":
        return OcrCandidateOrigin.ANCHORED_FUZZY
    if method == "LABELED_EXACT" or bool(candidate.anchor_text):
        return OcrCandidateOrigin.ANCHORED_EXACT
    if method == "NUMERIC_PATTERN" or not candidate.labeled:
        return OcrCandidateOrigin.UNANCHORED_PATTERN
    return OcrCandidateOrigin.ANCHORED_EXACT


def decide_unanchored_acceptance(
    policy: UnanchoredCodeCandidatePolicy | str | None,
) -> OcrCandidateAcceptance:
    raw = getattr(policy, "value", policy)
    key = str(raw or "").strip().upper()
    if key == UnanchoredCodeCandidatePolicy.REJECT.value:
        return OcrCandidateAcceptance.REJECT
    if key == UnanchoredCodeCandidatePolicy.ALLOW_FOR_MANUAL_REVIEW.value:
        return OcrCandidateAcceptance.MANUAL_REVIEW
    if key == UnanchoredCodeCandidatePolicy.ALLOW_IF_UNIQUE_AND_STRONG.value:
        # Uniqueness / strength gates remain in ranking + validator.
        return OcrCandidateAcceptance.AUTO_ACCEPT
    # Fail closed: unknown policy → manual review (never silent auto-resolve).
    return OcrCandidateAcceptance.MANUAL_REVIEW


def decide_candidate_acceptance(
    origin: OcrCandidateOrigin,
    *,
    unanchored_policy: UnanchoredCodeCandidatePolicy | str | None,
) -> OcrCandidateAcceptance:
    if origin is OcrCandidateOrigin.UNANCHORED_PATTERN:
        return decide_unanchored_acceptance(unanchored_policy)
    return OcrCandidateAcceptance.AUTO_ACCEPT


__all__ = [
    "OcrCandidateAcceptance",
    "OcrCandidateOrigin",
    "classify_field_candidate_origin",
    "classify_ocr_field_origin",
    "decide_candidate_acceptance",
    "decide_unanchored_acceptance",
]
