"""SEGMENT mappings require an explicit non-negative segment_index."""

from __future__ import annotations

import pytest

from src.application.services.image_processing.extraction_profile_configuration import (
    ExtractionProfileConfigurationError,
    parse_extraction_configuration,
)
from src.application.services.label_validation.label_validation_service import (
    LabelProfileConfigurationError,
    validate_extraction_configuration_for_code_scan,
)


def _parse_and_validate(raw: dict):
    cfg = parse_extraction_configuration(raw)
    validate_extraction_configuration_for_code_scan(cfg)
    return cfg


def _segmented_raw(mappings: list[dict], *, expected_segment_count: int = 3) -> dict:
    return {
        "configuration_schema_version": 2,
        "recognition_mode": "MINIMAL",
        "internal_code_sources": [],
        "quantity_rules": {"required": False, "minimum": 1, "maximum": 999, "allow_decimals": False},
        "accepted_barcode_formats": ["QR"],
        "required_fields": ["label_id"],
        "deterministic": {
            "payload_structure": "SEGMENTED",
            "delimiter": "|",
            "expected_segment_count": expected_segment_count,
            "expected_prefix": "PRD",
            "character_set": "ALPHANUMERIC",
            "field_mappings": mappings,
            "normalization": {"trim_outer_whitespace": True, "case_normalization": "NONE"},
        },
    }


def test_reordered_mappings_keep_explicit_indexes() -> None:
    cfg = _parse_and_validate(
        _segmented_raw(
            [
                {"target": "quantity", "source": "SEGMENT", "segment_index": 2},
                {"target": "label_id", "source": "SEGMENT", "segment_index": 0},
                {"target": "sku", "source": "SEGMENT", "segment_index": 1},
            ]
        )
    )
    assert cfg.deterministic is not None
    by_target = {rule.target: rule.segment_index for rule in cfg.deterministic.field_mappings}
    assert by_target == {"quantity": 2, "label_id": 0, "sku": 1}


def test_duplicate_mapping_targets_rejected() -> None:
    with pytest.raises(ExtractionProfileConfigurationError) as exc:
        parse_extraction_configuration(
            _segmented_raw(
                [
                    {"target": "label_id", "source": "SEGMENT", "segment_index": 0},
                    {"target": "label_id", "source": "SEGMENT", "segment_index": 1},
                ]
            )
        )
    assert exc.value.code == "LABEL_FIELD_MAPPING_INVALID"
    assert "duplicate" in exc.value.message


def test_missing_segment_index_rejected() -> None:
    with pytest.raises((ExtractionProfileConfigurationError, LabelProfileConfigurationError)) as exc:
        _parse_and_validate(
            _segmented_raw(
                [
                    {"target": "label_id", "source": "SEGMENT"},
                    {"target": "quantity", "source": "SEGMENT", "segment_index": 1},
                ]
            )
        )
    assert "segment_index" in exc.value.message


def test_decimal_segment_index_not_truncated() -> None:
    with pytest.raises(ExtractionProfileConfigurationError) as exc:
        parse_extraction_configuration(
            _segmented_raw(
                [{"target": "label_id", "source": "SEGMENT", "segment_index": 1.5}]
            )
        )
    assert "integer" in exc.value.message


def test_out_of_range_segment_index_rejected() -> None:
    with pytest.raises((ExtractionProfileConfigurationError, LabelProfileConfigurationError)) as exc:
        _parse_and_validate(
            _segmented_raw(
                [
                    {"target": "label_id", "source": "SEGMENT", "segment_index": 0},
                    {"target": "sku", "source": "SEGMENT", "segment_index": 5},
                ],
                expected_segment_count=3,
            )
        )
    assert "out of range" in exc.value.message
