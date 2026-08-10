"""Detect SQL Server unique / duplicate key violations without string-matching in use cases."""

from __future__ import annotations


def is_sql_unique_violation(exc: BaseException) -> bool:
    """True for SQL Server unique index / constraint violations (2601, 2627)."""
    # pyodbc: args[0] may be a list of error tuples; also check nested causes.
    codes: set[str] = set()
    messages: list[str] = []

    def _collect(err: BaseException) -> None:
        messages.append(str(err).lower())
        args = getattr(err, "args", ())
        for arg in args:
            if isinstance(arg, (list, tuple)):
                for item in arg:
                    if isinstance(item, (list, tuple)) and len(item) >= 2:
                        codes.add(str(item[0]))
                        messages.append(str(item[1]).lower())
                    else:
                        messages.append(str(item).lower())
            else:
                messages.append(str(arg).lower())
        cause = getattr(err, "__cause__", None)
        if isinstance(cause, BaseException):
            _collect(cause)
        ctx = getattr(err, "__context__", None)
        if isinstance(ctx, BaseException) and ctx is not cause:
            _collect(ctx)

    _collect(exc)
    if "2601" in codes or "2627" in codes:
        return True
    blob = " ".join(messages)
    return (
        "2627" in blob
        or "2601" in blob
        or "unique" in blob
        or "duplicate key" in blob
        or "duplicate" in blob and "key" in blob
    )
