"""Map process-start ``ValueError`` messages to structured HTTP errors (never 500)."""

from __future__ import annotations

from src.api.constants.error_wire import (
    HTTP_DETAIL_SUPPLIER_NOT_RESOLVED,
    HTTP_DETAIL_SUPPLIER_PROMPT_REQUIRED,
)
from src.api.errors.structured_api_http import (
    PROCESS_VALIDATION_FAILED,
    SUPPLIER_NOT_RESOLVED,
    SUPPLIER_PROMPT_REQUIRED,
    StructuredApiHttpError,
)


def structured_process_value_error(exc: ValueError) -> StructuredApiHttpError:
    """Map process-start configuration ValueErrors to structured 422.

    Shared by ``POST .../process`` and ``POST .../reprocess`` so both surfaces
    return the same ``code``/``detail`` contract (e.g. ``SUPPLIER_PROMPT_REQUIRED``).
    """
    msg = str(exc).strip() or "Invalid process request"
    code = PROCESS_VALIDATION_FAILED
    detail = msg
    if ":" in msg:
        head, rest = msg.split(":", 1)
        head = head.strip()
        if head and head == head.upper() and all(c.isalnum() or c == "_" for c in head):
            code = head
            detail = rest.strip() or msg
    if code == SUPPLIER_PROMPT_REQUIRED:
        detail = HTTP_DETAIL_SUPPLIER_PROMPT_REQUIRED
    elif code == SUPPLIER_NOT_RESOLVED:
        detail = HTTP_DETAIL_SUPPLIER_NOT_RESOLVED
    return StructuredApiHttpError(422, error_code=code, detail=detail)
