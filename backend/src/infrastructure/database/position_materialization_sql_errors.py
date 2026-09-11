"""Typed, redacted classification of SQL materialization failures."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

ACTIVE_IDENTITY_INDEX = "UQ_aisle_locations_client_aisle_normalized_code_active"
LEDGER_IDEMPOTENCY_INDEX = "UQ_pmr_client_idempotency_key"
KNOWN_UNIQUE_CONSTRAINTS = frozenset({ACTIVE_IDENTITY_INDEX, LEDGER_IDEMPOTENCY_INDEX})


class SqlFailureKind(str, Enum):
    IDENTITY_CONFLICT = "IDENTITY_CONFLICT"
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
    RETRYABLE = "RETRYABLE"
    INVARIANT_VIOLATION = "INVARIANT_VIOLATION"


@dataclass(frozen=True)
class SqlFailureClassification:
    kind: SqlFailureKind
    native_code: int | None = None
    sqlstate: str | None = None
    constraint_name: str | None = None


_NATIVE_CODE = re.compile(r"(?<!\d)(547|1205|2601|2627|2628|8152)(?!\d)")
_SQLSTATE = re.compile(r"(?<![A-Z0-9])(40001|HYT00|HYT01|08[A-Z0-9]{3})(?![A-Z0-9])")


def _diagnostic_tokens(exc: BaseException) -> list[str]:
    tokens: list[str] = []
    seen: set[int] = set()

    def visit(value: Any) -> None:
        if id(value) in seen:
            return
        seen.add(id(value))
        if isinstance(value, BaseException):
            for arg in value.args:
                visit(arg)
            if value.__cause__ is not None:
                visit(value.__cause__)
            if value.__context__ is not None and value.__context__ is not value.__cause__:
                visit(value.__context__)
        elif isinstance(value, (list, tuple)):
            for item in value:
                visit(item)
        elif isinstance(value, (str, int)):
            tokens.append(str(value))

    visit(exc)
    return tokens


def classify_sql_failure(exc: BaseException) -> SqlFailureClassification:
    """Classify diagnostics while returning no database message text."""
    tokens = _diagnostic_tokens(exc)
    blob = " ".join(tokens)
    native_match = _NATIVE_CODE.search(blob)
    native_code = int(native_match.group(1)) if native_match else None
    state_match = _SQLSTATE.search(blob.upper())
    sqlstate = state_match.group(1) if state_match else None
    constraint = next((name for name in KNOWN_UNIQUE_CONSTRAINTS if name in blob), None)

    if native_code in {2601, 2627} and constraint == ACTIVE_IDENTITY_INDEX:
        kind = SqlFailureKind.IDENTITY_CONFLICT
    elif native_code in {2601, 2627} and constraint == LEDGER_IDEMPOTENCY_INDEX:
        kind = SqlFailureKind.IDEMPOTENCY_CONFLICT
    elif native_code == 1205 or sqlstate in {"40001", "HYT00", "HYT01"}:
        kind = SqlFailureKind.RETRYABLE
    elif sqlstate is not None and sqlstate.startswith("08"):
        kind = SqlFailureKind.RETRYABLE
    else:
        kind = SqlFailureKind.INVARIANT_VIOLATION
    return SqlFailureClassification(
        kind=kind,
        native_code=native_code,
        sqlstate=sqlstate,
        constraint_name=constraint,
    )
