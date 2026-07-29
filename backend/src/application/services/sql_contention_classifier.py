"""Classify SQL / DB driver errors for recovery CAS boundaries (no string hunting in use cases)."""

from __future__ import annotations

from typing import Any


def is_transient_sql_contention(exc: BaseException) -> bool:
    """True for deadlock / serialization failures that callers may map to LOST_CAS.

    Inspects typed driver attributes when present (pyodbc ``args``, SQLSTATE) before
    falling back to well-known native codes — never used as a success path.
    """
    # pyodbc: exc.args[0] is often ('40001', '[...] ... 1205 ...')
    args = getattr(exc, "args", ()) or ()
    for item in args:
        text = str(item)
        upper = text.upper()
        if "40001" in upper or "1205" in upper or "DEADLOCK" in upper:
            return True
    # Native error code attribute used by some wrappers
    native = getattr(exc, "sqlstate", None) or getattr(exc, "sql_state", None)
    if native is not None and str(native).upper() in {"40001", "40P01"}:
        return True
    code = getattr(exc, "args", None)
    if isinstance(code, tuple) and code:
        first = code[0]
        if isinstance(first, str) and first.upper() in {"40001", "40P01"}:
            return True
    # Nested cause
    cause = getattr(exc, "__cause__", None)
    if cause is not None and cause is not exc:
        return is_transient_sql_contention(cause)
    return False


def is_unique_retry_of_violation(exc: BaseException) -> bool:
    """True when a unique index on ``retry_of_job_id`` rejected a second child."""
    text = str(exc).lower()
    if "ux_inventory_jobs_retry_of" in text:
        return True
    if "duplicate" in text and "retry_of" in text:
        return True
    # SQL Server unique violation
    args: Any = getattr(exc, "args", ()) or ()
    for item in args:
        blob = str(item).lower()
        if "2627" in blob or "2601" in blob:
            if "retry_of" in blob or "ux_inventory_jobs_retry_of" in blob:
                return True
    cause = getattr(exc, "__cause__", None)
    if cause is not None and cause is not exc:
        return is_unique_retry_of_violation(cause)
    return False
