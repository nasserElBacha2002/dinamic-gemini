"""Shared quantity completeness matrix — backend must match contracts JSON."""

from __future__ import annotations

from dataclasses import replace

from src.application.services.label_validation.quantity_completeness import (
    load_quantity_completeness_matrix,
    matrix_row_to_decision,
)
from src.application.services.label_validation.recognition_completeness import (
    evaluate_recognition_completeness,
)
from src.domain.client_supplier.extraction_profile import (
    MissingQuantityAction,
    QuantityExtractionRules,
    QuantityPresence,
    minimal_supplier_item_configuration,
    minimal_supplier_position_configuration,
)
from src.domain.label_profiles.kinds import LabelKind


def _config_from_row(row: dict):
    kind = LabelKind(row["kind"])
    base = (
        minimal_supplier_position_configuration()
        if kind is LabelKind.POSITION
        else minimal_supplier_item_configuration()
    )
    rules = QuantityExtractionRules(
        aliases=(),
        required=bool(row["required"]),
        expected_presence=QuantityPresence(row["expected_presence"]),
        missing_quantity_action=MissingQuantityAction(row["missing_quantity_action"]),
        allow_external_fallback=bool(row["allow_external_fallback"]),
        allow_decimals=False,
        default_value=None,
        allowed_spatial_relations=(),
    )
    return replace(
        base,
        quantity_rules=rules,
        required_fields=tuple(row.get("required_fields") or ()),
    )


def test_quantity_completeness_matrix_matches_evaluator() -> None:
    data = load_quantity_completeness_matrix()
    assert data["rows"], "quantity completeness matrix must not be empty"
    for row in data["rows"]:
        decision = matrix_row_to_decision(row)
        expected = row["expected"]
        assert decision.quantity_required_for_completion is expected[
            "quantity_required_for_completion"
        ], row["id"]
        completeness = evaluate_recognition_completeness(
            kind=LabelKind(row["kind"]),
            configuration=_config_from_row(row),
            fields=row["fields"],
        )
        assert completeness.identity_complete is expected["identity_complete"], row["id"]
        assert completeness.completion_complete is expected["completion_complete"], row["id"]
        assert completeness.persistence_complete is expected["persistence_complete"], row["id"]
        assert list(completeness.missing_completion_fields) == expected[
            "missing_completion_fields"
        ], row["id"]
        assert completeness.fallback_eligible is expected["fallback_eligible"], row["id"]
        quantity_present = row["fields"].get("quantity") is not None
        assert (
            decision.fallback_eligible(
                identity_complete=completeness.identity_complete,
                quantity_present=quantity_present,
            )
            is expected["fallback_eligible"]
        ), row["id"]
