"""Completeness evaluator + field-level CODE_SCAN/Vision merge."""

from __future__ import annotations

from src.application.services.label_validation.field_level_merge import merge_recognition_fields
from src.application.services.label_validation.recognition_completeness import (
    evaluate_recognition_completeness,
)
from src.domain.client_supplier.extraction_profile import (
    CharacterSetPolicy,
    inventory_count_item_configuration,
    minimal_supplier_item_configuration,
    minimal_supplier_position_configuration,
)
from src.domain.label_profiles.kinds import LabelKind


def test_minimal_identity_only_completeness() -> None:
    cfg = minimal_supplier_item_configuration(expected_prefix="PRD", exact_length=10)
    out = evaluate_recognition_completeness(
        kind=LabelKind.ITEM,
        configuration=cfg,
        fields={"label_id": "PRD-123456", "quantity": None},
    )
    assert out.identity_complete is True
    assert out.completion_complete is True  # RESOLVE_CODE_ONLY
    assert out.persistence_complete is True


def test_optional_pending_review_does_not_require_quantity() -> None:
    """Legacy OPTIONAL + PENDING_MANUAL_REVIEW must not block identity-only resolve."""
    from src.domain.client_supplier.extraction_profile import (
        MissingQuantityAction,
        QuantityPresence,
        manual_review_item_configuration,
    )

    cfg = manual_review_item_configuration(expected_prefix="ASI", exact_length=10)
    assert cfg.quantity_rules.expected_presence is QuantityPresence.OPTIONAL
    assert (
        cfg.quantity_rules.missing_quantity_action
        is MissingQuantityAction.PENDING_MANUAL_REVIEW
    )
    out = evaluate_recognition_completeness(
        kind=LabelKind.ITEM,
        configuration=cfg,
        fields={"label_id": "ASI-2W5H8D", "quantity": None},
    )
    assert out.identity_complete is True
    assert out.completion_complete is True
    assert out.persistence_complete is True


def test_inventory_enrichment_requires_quantity_for_completion() -> None:
    cfg = inventory_count_item_configuration(expected_prefix="PRD", exact_length=10)
    out = evaluate_recognition_completeness(
        kind=LabelKind.ITEM,
        configuration=cfg,
        fields={"label_id": "PRD-123456", "quantity": None},
    )
    assert out.identity_complete is True
    assert out.completion_complete is False
    assert "quantity" in out.missing_completion_fields
    assert out.persistence_complete is False


def test_simple_position_completeness() -> None:
    cfg = minimal_supplier_position_configuration(
        expected_prefix="LOC",
        exact_length=10,
        character_set=CharacterSetPolicy.ALPHANUMERIC_WITH_HYPHEN,
    )
    out = evaluate_recognition_completeness(
        kind=LabelKind.POSITION,
        configuration=cfg,
        fields={"position_id": "LOC-A01-02"},
    )
    assert out.identity_complete is True
    assert out.completion_complete is True
    assert out.persistence_complete is True


def test_field_merge_preserves_code_scan_identity() -> None:
    merged = merge_recognition_fields(
        confirmed={"label_id": "PRD-123456", "quantity": None},
        confirmed_sources={"label_id": "CODE_SCAN"},
        enrichment={"label_id": "OTHER-ID", "quantity": 24},
        enrichment_source="VISION",
        missing_fields=("quantity",),
    )
    assert merged.fields["label_id"] == "PRD-123456"
    assert merged.fields["quantity"] == 24
    assert merged.field_sources["label_id"] == "CODE_SCAN"
    assert merged.field_sources["quantity"] == "VISION"
    assert "label_id" in merged.overwritten_blocked


def test_field_merge_fills_only_missing() -> None:
    merged = merge_recognition_fields(
        confirmed={"label_id": "PRD-123456", "sku": "SKU1", "quantity": 10},
        confirmed_sources={"label_id": "CODE_SCAN", "sku": "CODE_SCAN", "quantity": "CODE_SCAN"},
        enrichment={"quantity": 99, "sku": "VISION-SKU"},
        enrichment_source="VISION",
        missing_fields=("quantity",),
    )
    assert merged.fields["quantity"] == 10
    assert merged.fields["sku"] == "SKU1"
    assert merged.filled_from_enrichment == ()
