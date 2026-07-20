"""Map OCR field candidates → profile FieldCandidate + JSON-safe evidence."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from enum import Enum
from typing import Any

from src.application.services.image_processing.ocr_field_extractor import (
    OcrFieldCandidate,
    OcrFieldKind,
)
from src.application.services.image_processing.profile_aware_processing_result_validator import (
    FieldCandidate,
)


def serialize_ocr_candidate_evidence(value: Any) -> Any:
    """Convert OCR / domain objects to JSON-primitive structures."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Enum):
        return getattr(value, "value", str(value))
    if isinstance(value, (list, tuple)):
        return [serialize_ocr_candidate_evidence(v) for v in value]
    if isinstance(value, dict):
        return {str(k): serialize_ocr_candidate_evidence(v) for k, v in value.items()}
    if is_dataclass(value) and not isinstance(value, type):
        return serialize_ocr_candidate_evidence(asdict(value))
    if hasattr(value, "left") and hasattr(value, "top") and hasattr(value, "width"):
        try:
            return {
                "left": int(value.left),
                "top": int(value.top),
                "width": int(value.width),
                "height": int(getattr(value, "height", 0) or 0),
            }
        except (TypeError, ValueError):
            return str(value)
    return str(value)


class OcrCandidateToFieldCandidateMapper:
    """Typed mapper from OcrFieldCandidate → FieldCandidate (no final status decisions)."""

    def map_code(self, candidate: OcrFieldCandidate) -> FieldCandidate | None:
        method = candidate.extraction_method or "LABELED_EXACT"
        source = "INTERNAL_CODE"
        labeled = (
            "label" in (candidate.source or "")
            or str(candidate.source).endswith("_label")
            or method in ("LABELED_EXACT", "LABELED_FUZZY")
        )
        if candidate.source == "numeric_pattern" or method == "NUMERIC_PATTERN":
            source = "INTERNAL_CODE"
            labeled = False
        elif candidate.kind is OcrFieldKind.EAN or candidate.source in (
            "ean_label",
            "bare_ean",
        ):
            source = "EAN"
            labeled = candidate.source == "ean_label"
        elif candidate.kind is OcrFieldKind.ARTICLE or candidate.source == "article_label":
            source = "ARTICLE"
            labeled = True
        elif candidate.kind is OcrFieldKind.PRODUCT or candidate.source == "product_label":
            source = "PRODUCT"
            labeled = True
        elif candidate.kind is OcrFieldKind.INTERNAL_CODE:
            source = "INTERNAL_CODE"
        else:
            return None

        confidence = candidate.confidence
        score = float(confidence) if confidence is not None else 0.5
        return FieldCandidate(
            source_key=source,
            value=str(candidate.value or ""),
            evidence_score=score,
            labeled=labeled,
            extraction_method=method,
            spatial_relation=candidate.spatial_relation,
            normalized_distance=candidate.normalized_distance,
            anchor_text=candidate.anchor_text,
        )

    def map_quantity(self, candidate: OcrFieldCandidate) -> FieldCandidate:
        confidence = candidate.confidence
        score = float(confidence) if confidence is not None else 0.5
        return FieldCandidate(
            source_key="QUANTITY",
            value=str(candidate.value or ""),
            evidence_score=score,
            labeled=True,
            extraction_method=candidate.extraction_method or "LABELED_EXACT",
            spatial_relation=candidate.spatial_relation,
            normalized_distance=candidate.normalized_distance,
            anchor_text=candidate.anchor_text,
        )

    def map_code_list(
        self, candidates: list[OcrFieldCandidate]
    ) -> list[FieldCandidate]:
        out: list[FieldCandidate] = []
        for cand in candidates:
            mapped = self.map_code(cand)
            if mapped is not None:
                out.append(mapped)
        return out

    def map_quantity_list(
        self, candidates: list[OcrFieldCandidate]
    ) -> list[FieldCandidate]:
        return [self.map_quantity(c) for c in candidates]


__all__ = [
    "OcrCandidateToFieldCandidateMapper",
    "serialize_ocr_candidate_evidence",
]
