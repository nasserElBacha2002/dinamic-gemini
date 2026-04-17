"""Structured v3 client errors: additive ``code`` + unchanged ``detail`` (HTTP body).

Registered on the FastAPI app via :func:`src.api.server.structured_api_http_error_handler`.

--------------------------------------------------------------------
CRITICAL: two coexisting error JSON shapes (partial rollout)
--------------------------------------------------------------------

**Structured** (only for exceptions raised as :class:`StructuredApiHttpError` and handled
by ``structured_api_http_error_handler``)::

    {"code": "INVENTORY_NOT_FOUND", "detail": "Inventory not found"}

**Legacy** (default FastAPI / Starlette ``HTTPException`` handler, validation errors, auth,
Category B mapper branches, Category C route-local errors, etc.)::

    {"detail": "..."}   # or FastAPI validation ``{"detail": [...]}``

**Do not assume** that all HTTP errors, all 404s, or all mapper-covered errors include
``code``. Only the **Category A stable not-found** subset in :mod:`src.api.errors.error_mapping`
(and the global unhandled 500) use structured bodies in this phase. Adding ``code`` elsewhere
requires an explicit compatibility review.

Broader ``HTTPException`` defaults are unchanged for compatibility.
"""

from __future__ import annotations

from fastapi import HTTPException

# Machine-readable codes (uppercase snake_case). Add new values only with API compatibility review.
INVENTORY_NOT_FOUND = "INVENTORY_NOT_FOUND"
AISLE_NOT_FOUND = "AISLE_NOT_FOUND"
POSITION_NOT_FOUND = "POSITION_NOT_FOUND"
PRODUCT_NOT_FOUND = "PRODUCT_NOT_FOUND"
VISUAL_REFERENCE_NOT_FOUND = "VISUAL_REFERENCE_NOT_FOUND"
INTERNAL_SERVER_ERROR = "INTERNAL_SERVER_ERROR"


class StructuredApiHttpError(HTTPException):
    """HTTP error serialized as ``{"code": "<error_code>", "detail": "<detail>"}``.

    Subclasses Starlette/FastAPI :class:`HTTPException` so call sites and ``pytest.raises``
    patterns remain valid; a dedicated exception handler emits the flat JSON shape.
    """

    def __init__(self, status_code: int, *, error_code: str, detail: str) -> None:
        self.error_code = error_code
        super().__init__(status_code=status_code, detail=detail)
