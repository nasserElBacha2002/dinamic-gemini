"""Unit tests for the Phase 3 per-image code detection consolidator."""

from __future__ import annotations

from src.application.services.image_processing.code_detection_consolidator import (
    CodeConsolidationStatus,
    CodeDetectionConsolidator,
    CodeDetectionInput,
)
from src.application.services.image_processing.encoded_label_payload_parser import (
    LabelPayloadFormat,
    ParsedLabelPayload,
)


def _det(index: int, code: str | None, qty: int | None, raw: str = "") -> CodeDetectionInput:
    return CodeDetectionInput(
        symbology="QR_CODE",
        raw_value=raw or (code or ""),
        parsed=ParsedLabelPayload(
            format=LabelPayloadFormat.PIPE,
            version=None,
            internal_code=code,
            quantity=qty,
            raw_value=raw or (code or ""),
        ),
        detection_index=index,
    )


def test_no_detections() -> None:
    result = CodeDetectionConsolidator().consolidate([])
    assert result.status is CodeConsolidationStatus.NO_DETECTIONS


def test_single_resolved() -> None:
    result = CodeDetectionConsolidator().consolidate([_det(0, "ABC", 5)])
    assert result.status is CodeConsolidationStatus.RESOLVED
    assert result.internal_code == "ABC"
    assert result.quantity == 5
    assert result.selected_detection_index == 0


def test_same_code_twice_is_one_logical_label() -> None:
    result = CodeDetectionConsolidator().consolidate([_det(0, "ABC", 5), _det(1, "ABC", 5)])
    assert result.status is CodeConsolidationStatus.RESOLVED
    assert result.internal_code == "ABC"
    assert result.quantity == 5


def test_distinct_codes_require_manual_review() -> None:
    result = CodeDetectionConsolidator().consolidate([_det(0, "ABC", 5), _det(1, "XYZ", 3)])
    assert result.status is CodeConsolidationStatus.MULTIPLE_DISTINCT_CODES
    assert set(result.distinct_codes) == {"ABC", "XYZ"}


def test_missing_quantity() -> None:
    result = CodeDetectionConsolidator().consolidate([_det(0, "ABC", None)])
    assert result.status is CodeConsolidationStatus.MISSING_QUANTITY
    assert result.internal_code == "ABC"
    assert result.quantity is None


def test_quantity_conflict_same_code() -> None:
    result = CodeDetectionConsolidator().consolidate([_det(0, "ABC", 5), _det(1, "ABC", 6)])
    assert result.status is CodeConsolidationStatus.QUANTITY_CONFLICT
    assert result.internal_code == "ABC"


def test_detections_without_valid_code() -> None:
    result = CodeDetectionConsolidator().consolidate([_det(0, None, None, raw="garbage")])
    assert result.status is CodeConsolidationStatus.NO_VALID_CODE
