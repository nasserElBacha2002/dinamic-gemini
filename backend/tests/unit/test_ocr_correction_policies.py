"""Unit tests for OCR correction policies (defaults, anchors, variants, quantity)."""

from __future__ import annotations

import io

from PIL import Image, ImageDraw

from src.application.services.image_processing.label_region_detector import LabelRegionDetector
from src.application.services.image_processing.missing_quantity_resolution_policy import (
    MissingQuantityResolutionPolicy,
)
from src.application.services.image_processing.ocr_spatial_relation_evaluator import (
    BoundingBox,
    OcrSpatialRelationEvaluator,
)
from src.application.services.image_processing.ocr_variant_plan import (
    VARIANT_PLAN_VERSION,
    build_ocr_variant_plan,
)
from src.domain.client_supplier.extraction_profile import (
    AnchorMatchPolicy,
    LabelBackgroundHint,
    LabelDetectionRules,
    MissingQuantityAction,
    QuantityExtractionRules,
    QuantityPresence,
    default_extraction_configuration,
    inventory_seven_digit_internal_code_template,
)
from src.domain.image_processing.contracts import ImageResultStatus


def test_default_is_agnostic_no_exact_length_7() -> None:
    cfg = default_extraction_configuration()
    assert cfg.validation_rules.code.exact_length is None
    assert cfg.validation_rules.code.allow_letters is True
    assert cfg.validation_rules.code.allow_digits is True
    enabled = [s.field_key for s in cfg.internal_code_sources if s.enabled]
    assert enabled == ["INTERNAL_CODE", "EAN", "ARTICLE"]
    assert cfg.label_detection_rules.minimum_anchor_matches == 0
    assert cfg.label_detection_rules.anchor_match_policy is AnchorMatchPolicy.GEOMETRY_ONLY_ALLOWED


def test_seven_digit_template_is_opt_in() -> None:
    tpl = inventory_seven_digit_internal_code_template()
    assert tpl.validation_rules.code.exact_length == 7
    assert tpl.validation_rules.code.allow_letters is False
    assert tpl.label_detection_rules.expected_background is LabelBackgroundHint.LIGHT
    assert tpl.label_detection_rules.anchor_match_policy is AnchorMatchPolicy.ANCHORS_PREFERRED
    assert (
        tpl.validation_rules.code.unanchored_candidate_policy.value
        == "ALLOW_FOR_MANUAL_REVIEW"
    )
    assert any(
        s.field_key == "EAN" and s.enabled is False for s in tpl.internal_code_sources
    )


def test_variant_plan_prioritizes_preprocess_then_psm() -> None:
    plan = build_ocr_variant_plan(max_total_engine_calls=3)
    assert VARIANT_PLAN_VERSION == "v1"
    assert [s.name for s in plan] == [
        "original_psm6",
        "adaptive_threshold_psm6",
        "adaptive_threshold_psm11",
    ]


def test_anchors_required_rejects_geometry_only_when_light_ocr_ran() -> None:
    class _FakeReader:
        def read(self, image, context):  # noqa: ANN001
            class R:
                full_text = "PACKAGING ONLY 60x60"

            return R()

    img = Image.new("RGB", (400, 300), color=(40, 40, 40))
    draw = ImageDraw.Draw(img)
    draw.rectangle((120, 80, 280, 220), fill=(245, 245, 245))
    buf = io.BytesIO()
    img.save(buf, format="PNG")

    detector = LabelRegionDetector(
        rules=LabelDetectionRules(
            enabled=True,
            expected_background=LabelBackgroundHint.LIGHT,
            primary_anchors=("CODIGO INTERNO",),
            minimum_anchor_matches=1,
            anchor_match_policy=AnchorMatchPolicy.ANCHORS_REQUIRED,
            allow_full_image_fallback=False,
        ),
        light_ocr_reader=_FakeReader(),
    )
    result = detector.detect(buf.getvalue())
    assert result.detected is False
    assert result.light_ocr_executed is True
    assert result.anchor_requirement_met is False
    assert result.failure_reason == "LABEL_ANCHORS_INSUFFICIENT"


def test_geometry_only_allowed_selects_without_anchors() -> None:
    img = Image.new("RGB", (400, 300), color=(40, 40, 40))
    draw = ImageDraw.Draw(img)
    draw.rectangle((120, 80, 280, 220), fill=(245, 245, 245))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    detector = LabelRegionDetector(
        rules=LabelDetectionRules(
            enabled=True,
            expected_background=LabelBackgroundHint.LIGHT,
            minimum_anchor_matches=0,
            anchor_match_policy=AnchorMatchPolicy.GEOMETRY_ONLY_ALLOWED,
            allow_full_image_fallback=True,
        ),
        light_ocr_reader=None,
    )
    result = detector.detect(buf.getvalue())
    assert result.detected is True


def test_missing_quantity_policy_manual_review() -> None:
    decision = MissingQuantityResolutionPolicy().resolve(
        rules=QuantityExtractionRules(
            expected_presence=QuantityPresence.ALWAYS,
            missing_quantity_action=MissingQuantityAction.PENDING_MANUAL_REVIEW,
            allow_external_fallback=True,
        ),
        has_valid_internal_code=True,
        quantity_found=False,
    )
    assert decision is not None
    assert decision.status is ImageResultStatus.PENDING_MANUAL_REVIEW
    assert decision.error_code == "MISSING_QUANTITY"


def test_spatial_below_relation() -> None:
    ev = OcrSpatialRelationEvaluator(image_diagonal=1000.0)
    anchor = BoundingBox(10, 10, 100, 20)
    value = BoundingBox(20, 40, 80, 20)
    res = ev.evaluate(
        anchor=anchor,
        value=value,
        allowed=("BELOW", "NEAR"),
        maximum_anchor_distance_ratio=0.5,
    )
    assert res.relation == "BELOW"
    assert res.matches_allowed is True
