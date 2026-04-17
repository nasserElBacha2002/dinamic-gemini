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
``code``. Structured bodies come from :class:`StructuredApiHttpError` only (see
:mod:`src.api.errors.error_mapping` for which exception types map there).

**Rollout:** Category A stable not-founds, **selected** Category B job/conflict branches (Phase 3:
``detail`` is a **controlled template** from known use-case message shapes, not raw arbitrary
``str(exc)`` when patterns match), the global unhandled 500, plus any route that raises
:class:`StructuredApiHttpError` directly. Most mapper branches and all Category C routes remain
legacy ``{"detail": ...}`` or other shapes.

**Transition:** for structured errors, ``code`` is the stable machine identifier; ``detail`` is
the human-facing string (fixed for Category A, templated for structured Category B). New
clients should branch on ``code``; existing clients may keep reading ``detail`` only.

Broader plain ``HTTPException`` defaults are unchanged for compatibility.
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
# Phase 2 — selected Category B (detail remains str(exc); code is additive).
JOB_NOT_FOUND = "JOB_NOT_FOUND"
JOB_NOT_IN_AISLE_SCOPE = "JOB_NOT_IN_AISLE_SCOPE"
ACTIVE_JOB_EXISTS = "ACTIVE_JOB_EXISTS"
JOB_PROMOTION_NOT_ALLOWED = "JOB_PROMOTION_NOT_ALLOWED"


class StructuredApiHttpError(HTTPException):
    """HTTP error serialized as ``{"code": "<error_code>", "detail": "<detail>"}``.

    Subclasses Starlette/FastAPI :class:`HTTPException` so call sites and ``pytest.raises``
    patterns remain valid; a dedicated exception handler emits the flat JSON shape.
    """

    def __init__(self, status_code: int, *, error_code: str, detail: str) -> None:
        self.error_code = error_code
        super().__init__(status_code=status_code, detail=detail)
