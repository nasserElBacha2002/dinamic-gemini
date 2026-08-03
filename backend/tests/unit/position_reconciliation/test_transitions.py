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
        ("MISSING_SIGNATURE", PositionTransitionAction.KEEP_POSITION),
        ("DUPLICATE_POSITION_CODES", PositionTransitionAction.KEEP_POSITION),
        ("INVALID_SIGNATURE", PositionTransitionAction.CLEAR_POSITION),
        ("CLIENT_MISMATCH", PositionTransitionAction.CLEAR_POSITION),
        ("LABEL_INVALIDATED", PositionTransitionAction.CLEAR_POSITION),
        ("AMBIGUOUS_POSITION_DETECTION", PositionTransitionAction.CLEAR_POSITION),
        ("LEGACY_UNSIGNED_REQUIRES_REVIEW", PositionTransitionAction.SET_POSITION),
    ],
)
def test_transition_table(status, expected):
    assert resolve_position_transition(status) is expected
