"""MSSQL ``N'…'`` fragments for ``review_actions.action_type``.

Single source for persisted action-type spellings used in raw SQL. Values are
defined by ``ReviewActionType``; keep this module aligned when the enum changes.
"""

from __future__ import annotations

from src.domain.reviews.entities import ReviewActionType


def _nvarchar_literal(value: str) -> str:
    escaped = value.replace("'", "''")
    return f"N'{escaped}'"


def review_action_sql_in(types: tuple[ReviewActionType, ...]) -> str:
    """Comma-separated ``N'value'`` list for ``IN (...)``."""
    return ", ".join(_nvarchar_literal(t.value) for t in types)


def review_action_sql_eq(action: ReviewActionType) -> str:
    """Single ``N'value'`` for ``=`` comparisons."""
    return _nvarchar_literal(action.value)


# --- Common subsets (analytics / quality queries) ---

REVIEW_ACTION_TYPES_SETTLING: tuple[ReviewActionType, ...] = (
    ReviewActionType.CONFIRM,
    ReviewActionType.UPDATE_QUANTITY,
    ReviewActionType.UPDATE_SKU,
    ReviewActionType.MARK_UNKNOWN,
    ReviewActionType.CREATE_MANUAL_RESULT_FROM_IMAGE,
)

REVIEW_ACTION_TYPES_CORRECTION: tuple[ReviewActionType, ...] = (
    ReviewActionType.UPDATE_QUANTITY,
    ReviewActionType.UPDATE_SKU,
)

# Subset used in manual-intervention quality SQL (excludes ``update_position_code``; matches legacy query).
REVIEW_ACTION_TYPES_MANUAL_QUALITY_FILTER: tuple[ReviewActionType, ...] = (
    ReviewActionType.CONFIRM,
    ReviewActionType.UPDATE_QUANTITY,
    ReviewActionType.UPDATE_SKU,
    ReviewActionType.MARK_UNKNOWN,
    ReviewActionType.MARK_IMAGE_MISMATCH,
    ReviewActionType.DELETE_POSITION,
)

REVIEW_ACTION_TYPES_REVIEWED_POSITIONS: tuple[ReviewActionType, ...] = (
    ReviewActionType.CONFIRM,
    ReviewActionType.UPDATE_QUANTITY,
    ReviewActionType.UPDATE_SKU,
    ReviewActionType.MARK_UNKNOWN,
    ReviewActionType.MARK_IMAGE_MISMATCH,
    ReviewActionType.CREATE_MANUAL_RESULT_FROM_IMAGE,
)

SQL_IN_SETTLING_ACTIONS = review_action_sql_in(REVIEW_ACTION_TYPES_SETTLING)
SQL_IN_CORRECTION_ACTIONS = review_action_sql_in(REVIEW_ACTION_TYPES_CORRECTION)
SQL_IN_MANUAL_QUALITY_FILTER_ACTIONS = review_action_sql_in(
    REVIEW_ACTION_TYPES_MANUAL_QUALITY_FILTER
)
SQL_IN_REVIEWED_POSITIONS_ACTIONS = review_action_sql_in(REVIEW_ACTION_TYPES_REVIEWED_POSITIONS)

SQL_EQ_CONFIRM = review_action_sql_eq(ReviewActionType.CONFIRM)
SQL_EQ_UPDATE_QUANTITY = review_action_sql_eq(ReviewActionType.UPDATE_QUANTITY)
SQL_EQ_UPDATE_SKU = review_action_sql_eq(ReviewActionType.UPDATE_SKU)
SQL_EQ_MARK_UNKNOWN = review_action_sql_eq(ReviewActionType.MARK_UNKNOWN)
SQL_EQ_MARK_IMAGE_MISMATCH = review_action_sql_eq(ReviewActionType.MARK_IMAGE_MISMATCH)
SQL_EQ_DELETE_POSITION = review_action_sql_eq(ReviewActionType.DELETE_POSITION)
SQL_EQ_CREATE_MANUAL_RESULT_FROM_IMAGE = review_action_sql_eq(
    ReviewActionType.CREATE_MANUAL_RESULT_FROM_IMAGE
)
