"""Guard ``review_actions`` SQL fragments against ``ReviewActionType`` drift."""

from src.domain.reviews.entities import ReviewActionType
from src.domain.reviews.sql_literals import (
    SQL_EQ_CONFIRM,
    SQL_IN_CORRECTION_ACTIONS,
    SQL_IN_MANUAL_QUALITY_FILTER_ACTIONS,
    SQL_IN_SETTLING_ACTIONS,
    review_action_sql_eq,
    review_action_sql_in,
)


def test_sql_in_settling_matches_enum_subset_order() -> None:
    expected = ", ".join(
        f"N'{t.value}'"
        for t in (
            ReviewActionType.CONFIRM,
            ReviewActionType.UPDATE_QUANTITY,
            ReviewActionType.UPDATE_SKU,
            ReviewActionType.MARK_UNKNOWN,
            ReviewActionType.CREATE_MANUAL_RESULT_FROM_IMAGE,
        )
    )
    assert SQL_IN_SETTLING_ACTIONS == expected


def test_sql_eq_confirm_literal() -> None:
    assert SQL_EQ_CONFIRM == "N'confirm'"
    assert review_action_sql_eq(ReviewActionType.CONFIRM) == "N'confirm'"


def test_sql_in_corrections() -> None:
    assert "N'update_quantity'" in SQL_IN_CORRECTION_ACTIONS
    assert "N'update_sku'" in SQL_IN_CORRECTION_ACTIONS


def test_manual_quality_filter_excludes_update_position_code() -> None:
    assert "update_position_code" not in SQL_IN_MANUAL_QUALITY_FILTER_ACTIONS
    assert SQL_IN_MANUAL_QUALITY_FILTER_ACTIONS == review_action_sql_in(
        (
            ReviewActionType.CONFIRM,
            ReviewActionType.UPDATE_QUANTITY,
            ReviewActionType.UPDATE_SKU,
            ReviewActionType.MARK_UNKNOWN,
            ReviewActionType.MARK_IMAGE_MISMATCH,
            ReviewActionType.DELETE_POSITION,
        )
    )
