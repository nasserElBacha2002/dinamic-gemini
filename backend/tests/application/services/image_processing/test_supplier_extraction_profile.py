"""Unit tests for Phase 6 profile-aware validation + configuration parsing."""

from __future__ import annotations

import pytest

from src.application.services.image_processing.extraction_profile_configuration import (
    ExtractionProfileConfigurationError,
    parse_extraction_configuration,
)
from src.application.services.image_processing.label_geometry_normalizer import (
    validate_normalized_polygon,
)
from src.application.services.image_processing.profile_aware_processing_result_validator import (
    ExtractionValidationErrorCode,
    FieldCandidate,
    ProfileAwareProcessingResultValidator,
    ean_checksum_valid,
)
from src.application.services.image_processing.supplier_extraction_profile_resolver import (
    SupplierExtractionProfileResolver,
)
from src.domain.client_supplier.extraction_profile import default_extraction_configuration
from src.infrastructure.repositories.memory_supplier_extraction_profile_repository import (
    MemorySupplierExtractionProfileRepository,
)


def test_ean_checksum_valid_known_value() -> None:
    assert ean_checksum_valid("4006381333931") is True
    assert ean_checksum_valid("4006381333930") is False


def test_masol_style_ean_priority() -> None:
    cfg = parse_extraction_configuration(
        {
            "internal_code_sources": [
                {"field_key": "EAN", "priority": 1, "enabled": True},
                {"field_key": "INTERNAL_CODE", "priority": 2, "enabled": True},
            ],
            "forbidden_internal_code_sources": ["ARTICLE", "PRODUCT"],
            "quantity_rules": {
                "aliases": ["CANTIDAD", "QTY"],
                "required": True,
                "minimum": 1,
                "maximum": 999999,
                "default_value": None,
            },
            "required_fields": ["internal_code", "quantity"],
        }
    )
    v = ProfileAwareProcessingResultValidator(cfg)
    result = v.validate_resolved(
        code_candidates=[
            FieldCandidate("ARTICLE", "10334301"),
            FieldCandidate("EAN", "4006381333931"),
        ],
        quantity_candidates=[FieldCandidate("QUANTITY", "48")],
    )
    assert result.ok is True
    assert result.internal_code == "4006381333931"
    assert result.quantity == 48
    assert result.internal_code_source == "EAN"


def test_article_first_profile() -> None:
    cfg = parse_extraction_configuration(
        {
            "internal_code_sources": [
                {"field_key": "ARTICLE", "priority": 1},
                {"field_key": "SKU", "priority": 2},
            ],
            "quantity_rules": {"aliases": ["CANTIDAD"], "default_value": None},
        }
    )
    v = ProfileAwareProcessingResultValidator(cfg)
    result = v.validate_resolved(
        code_candidates=[
            FieldCandidate("EAN", "4006381333931"),
            FieldCandidate("ARTICLE", "10334301"),
        ],
        quantity_candidates=[FieldCandidate("CANTIDAD", "48")],
    )
    assert result.ok is True
    assert result.internal_code == "10334301"


def test_quantity_default_forbidden() -> None:
    with pytest.raises(ExtractionProfileConfigurationError) as exc:
        parse_extraction_configuration(
            {
                "internal_code_sources": [{"field_key": "EAN", "priority": 1}],
                "quantity_rules": {"default_value": 1},
            }
        )
    assert exc.value.code == "QUANTITY_DEFAULT_FORBIDDEN"


def test_ambiguous_code_same_priority_evidence() -> None:
    cfg = parse_extraction_configuration(
        {
            "internal_code_sources": [{"field_key": "EAN", "priority": 1}],
            "quantity_rules": {"default_value": None},
        }
    )
    v = ProfileAwareProcessingResultValidator(cfg)
    result = v.validate_resolved(
        code_candidates=[
            FieldCandidate("EAN", "4006381333931", evidence_score=1.0),
            FieldCandidate("EAN", "7791234567890", evidence_score=1.0),
        ],
        quantity_candidates=[FieldCandidate("QTY", "2")],
    )
    assert result.ok is False
    assert ExtractionValidationErrorCode.AMBIGUOUS_INTERNAL_CODE.value in result.errors


def test_no_default_quantity_invention() -> None:
    cfg = default_extraction_configuration()
    v = ProfileAwareProcessingResultValidator(cfg)
    result = v.validate_resolved(
        code_candidates=[FieldCandidate("INTERNAL_CODE", "ABC")],
        quantity_candidates=[],
    )
    assert result.ok is False
    assert result.quantity is None
    assert ExtractionValidationErrorCode.MISSING_QUANTITY.value in result.errors


def test_polygon_validation() -> None:
    poly = validate_normalized_polygon([[0.1, 0.1], [0.9, 0.1], [0.9, 0.5], [0.1, 0.5]])
    assert len(poly) == 4
    with pytest.raises(ValueError):
        validate_normalized_polygon([[0.1, 0.1], [0.2, 0.1]])  # too few
    with pytest.raises(ValueError):
        validate_normalized_polygon([[1.5, 0.1], [0.2, 0.1], [0.2, 0.2]])


def test_resolver_prefers_snapshot() -> None:
    repo = MemorySupplierExtractionProfileRepository()
    resolver = SupplierExtractionProfileResolver(repo, profiles_enabled=True)
    snap = {
        "supplier_profile_id": "p1",
        "supplier_profile_key": "default",
        "supplier_profile_version": 3,
        "client_id": "c1",
        "supplier_id": "s1",
        "configuration": default_extraction_configuration().to_public_dict(),
    }
    resolved = resolver.resolve_for_job(
        client_id="c1",
        supplier_id="s1",
        engine_params={"identification_execution": {"supplier_extraction_profile": snap}},
    )
    assert resolved.source == "SNAPSHOT"
    assert resolved.profile_version == 3


def test_resolver_default_when_disabled() -> None:
    resolver = SupplierExtractionProfileResolver(None, profiles_enabled=False)
    resolved = resolver.resolve_for_job(client_id="c1", supplier_id="s1")
    assert resolved.source == "DEFAULT"
    assert resolved.profile_key == "system_default"
