"""Unit tests for OCR candidate filters and label detection helpers."""

from __future__ import annotations

import io

from PIL import Image, ImageDraw

from src.application.services.image_processing.extraction_profile_configuration import (
    parse_extraction_configuration,
)
from src.application.services.image_processing.label_region_detector import LabelRegionDetector
from src.application.services.image_processing.ocr_candidate_filters import (
    OcrCandidateRejectReason,
    filter_internal_code_candidate,
    looks_like_measurement,
)
from src.application.services.image_processing.profile_aware_processing_result_validator import (
    FieldCandidate,
    ProfileAwareProcessingResultValidator,
)
from src.domain.client_supplier.extraction_profile import (
    CodeValidationRules,
    LabelDetectionRules,
)


def test_reject_measurement_pattern_60x60() -> None:
    assert looks_like_measurement("60x60") == OcrCandidateRejectReason.CODE_MEASUREMENT_PATTERN
    decision = filter_internal_code_candidate(
        "60x60",
        rules=CodeValidationRules(exact_length=7, allow_letters=False, reject_measurement_patterns=True),
    )
    assert decision.accepted is False
    assert decision.reason_code == OcrCandidateRejectReason.CODE_MEASUREMENT_PATTERN


def test_reject_unit_suffix() -> None:
    assert looks_like_measurement("600 mm") == OcrCandidateRejectReason.CODE_UNIT_SUFFIX


def test_reject_header_short_number() -> None:
    reason = looks_like_measurement("26", neighbor_text="INVENTARIO GENERAL 26")
    assert reason == OcrCandidateRejectReason.CODE_FORBIDDEN_CONTEXT


def test_exact_length_7_accepts() -> None:
    decision = filter_internal_code_candidate(
        "1428706",
        rules=CodeValidationRules(
            exact_length=7,
            allow_letters=False,
            allow_digits=True,
            reject_measurement_patterns=True,
        ),
    )
    assert decision.accepted is True


def test_exact_length_rejects_short() -> None:
    decision = filter_internal_code_candidate(
        "05",
        rules=CodeValidationRules(exact_length=7, allow_letters=False),
    )
    assert decision.accepted is False
    assert decision.reason_code == OcrCandidateRejectReason.CODE_LENGTH_NOT_EXACT


def test_preserve_leading_zeros_via_profile_validator() -> None:
    config = parse_extraction_configuration(
        {
            "internal_code_sources": [
                {"field_key": "INTERNAL_CODE", "priority": 1, "enabled": True}
            ],
            "quantity_rules": {"aliases": ["CANTIDAD"], "required": True, "minimum": 1},
            "validation_rules": {
                "code": {
                    "exact_length": 7,
                    "allow_letters": False,
                    "allow_digits": True,
                    "preserve_leading_zeros": True,
                    "reject_measurement_patterns": True,
                }
            },
            "label_detection_rules": {
                "enabled": True,
                "primary_anchors": ["CODIGO INTERNO"],
                "minimum_anchor_matches": 1,
            },
        }
    )
    validator = ProfileAwareProcessingResultValidator(config)
    result = validator.validate_resolved(
        code_candidates=[FieldCandidate("INTERNAL_CODE", "0123456", 0.9)],
        quantity_candidates=[FieldCandidate("QUANTITY", "12", 0.9)],
    )
    assert result.ok is True
    assert result.internal_code == "0123456"


def test_missing_quantity_keeps_code() -> None:
    config = parse_extraction_configuration(
        {
            "internal_code_sources": [
                {"field_key": "INTERNAL_CODE", "priority": 1, "enabled": True}
            ],
            "quantity_rules": {
                "aliases": ["CANTIDAD"],
                "required": True,
                "minimum": 1,
                "missing_quantity_action": "PENDING_MANUAL_REVIEW",
            },
            "validation_rules": {
                "code": {"exact_length": 7, "allow_letters": False, "allow_digits": True}
            },
        }
    )
    validator = ProfileAwareProcessingResultValidator(config)
    result = validator.validate_resolved(
        code_candidates=[FieldCandidate("INTERNAL_CODE", "1428706", 0.9)],
        quantity_candidates=[],
    )
    assert result.ok is False
    assert result.internal_code == "1428706"
    assert "MISSING_QUANTITY" in result.errors


def test_profile_rejects_measurement_as_code() -> None:
    config = parse_extraction_configuration(
        {
            "internal_code_sources": [
                {"field_key": "INTERNAL_CODE", "priority": 1, "enabled": True}
            ],
            "quantity_rules": {"aliases": ["CANTIDAD"], "required": True, "minimum": 1},
            "validation_rules": {
                "code": {
                    "exact_length": 7,
                    "allow_letters": False,
                    "allow_digits": True,
                    "reject_measurement_patterns": True,
                }
            },
        }
    )
    validator = ProfileAwareProcessingResultValidator(config)
    result = validator.validate_resolved(
        code_candidates=[FieldCandidate("INTERNAL_CODE", "60x60", 0.9)],
        quantity_candidates=[FieldCandidate("QUANTITY", "10", 0.9)],
    )
    assert result.ok is False
    assert "INVALID_INTERNAL_CODE" in result.errors


def _white_rect_image() -> bytes:
    img = Image.new("RGB", (400, 300), color=(40, 40, 40))
    draw = ImageDraw.Draw(img)
    draw.rectangle((120, 80, 280, 220), fill=(245, 245, 245))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_label_detector_finds_light_rectangle() -> None:
    from src.domain.client_supplier.extraction_profile import LabelBackgroundHint

    detector = LabelRegionDetector(
        rules=LabelDetectionRules(
            enabled=True,
            expected_background=LabelBackgroundHint.LIGHT,
            minimum_anchor_matches=0,
            allow_full_image_fallback=True,
        ),
        light_ocr_reader=None,
    )
    result = detector.detect(_white_rect_image())
    assert result.detected is True
    assert result.selected_candidate is not None
    assert result.selected_candidate.relative_area > 0


def test_label_detector_disabled_uses_fallback_flag() -> None:
    from src.domain.client_supplier.extraction_profile import LabelBackgroundHint

    detector = LabelRegionDetector(
        rules=LabelDetectionRules(
            enabled=False,
            expected_background=LabelBackgroundHint.LIGHT,
            allow_full_image_fallback=True,
        )
    )
    result = detector.detect(_white_rect_image())
    assert result.detected is False
    assert result.used_full_image_fallback is True
    assert result.failure_reason == "LABEL_DETECTION_DISABLED"
