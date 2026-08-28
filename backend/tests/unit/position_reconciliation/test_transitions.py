import pytest

from src.application.services.position_reconciliation.transitions import (
    resolve_position_transition,
)
from src.domain.position_reconciliation.entities import PositionTransitionAction


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("VALID", PositionTransitionAction.SET_POSITION),
        ("NO_LABEL", PositionTransitionAction.KEEP_POSITION),
        ("INVALID_JSON", PositionTransitionAction.KEEP_POSITION),
        ("UNSUPPORTED_VERSION", PositionTransitionAction.KEEP_POSITION),
        ("MISSING_SIGNATURE", PositionTransitionAction.CLEAR_POSITION),
        ("DUPLICATE_POSITION_CODES", PositionTransitionAction.KEEP_POSITION),
        ("INVALID_SIGNATURE", PositionTransitionAction.CLEAR_POSITION),
        ("CLIENT_MISMATCH", PositionTransitionAction.CLEAR_POSITION),
        ("LABEL_INVALIDATED", PositionTransitionAction.CLEAR_POSITION),
        ("AMBIGUOUS_POSITION_DETECTION", PositionTransitionAction.CLEAR_POSITION),
        # Explicit failed DINAMIC_POSITION detections clear forward-fill (unlike NO_LABEL).
        ("LABEL_NOT_FOUND", PositionTransitionAction.CLEAR_POSITION),
        ("INVALID_TYPE", PositionTransitionAction.CLEAR_POSITION),
        ("UNKNOWN_KEY_VERSION", PositionTransitionAction.CLEAR_POSITION),
        ("SIGNATURE_VALIDATION_SKIPPED", PositionTransitionAction.KEEP_POSITION),
        ("LEGACY_UNSIGNED_REQUIRES_REVIEW", PositionTransitionAction.SET_POSITION),
    ],
)
def test_transition_table(status, expected):
    assert resolve_position_transition(status) is expected


def test_sequence_set_then_explicit_invalid_clears_for_next_product():
    """SET A → explicit LABEL_NOT_FOUND → next product must not inherit A (CLEAR)."""
    assert resolve_position_transition("VALID") is PositionTransitionAction.SET_POSITION
    assert (
        resolve_position_transition("LABEL_NOT_FOUND")
        is PositionTransitionAction.CLEAR_POSITION
    )


def test_sequence_set_then_unknown_key_clears():
    assert resolve_position_transition("VALID") is PositionTransitionAction.SET_POSITION
    assert (
        resolve_position_transition("UNKNOWN_KEY_VERSION")
        is PositionTransitionAction.CLEAR_POSITION
    )


def test_sequence_set_then_catalog_hierarchy_mismatch_clears():
    """catalog_hierarchy_mismatch is signaled as INVALID_TYPE + CLEAR."""
    assert resolve_position_transition("VALID") is PositionTransitionAction.SET_POSITION
    assert resolve_position_transition("INVALID_TYPE") is PositionTransitionAction.CLEAR_POSITION


def test_no_label_keeps_position_unlike_explicit_invalid():
    assert resolve_position_transition("VALID") is PositionTransitionAction.SET_POSITION
    assert resolve_position_transition("NO_LABEL") is PositionTransitionAction.KEEP_POSITION
