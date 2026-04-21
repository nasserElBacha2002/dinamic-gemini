"""Structured v3 client errors: additive ``code`` + controlled human-facing ``detail`` (HTTP body).

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
legacy ``{"detail": ...}`` or other shapes. For ``JOB_NOT_FOUND`` specifically: canonical
``Job not found: <id>`` is kept when the raised message matches the vetted pattern; any other
``JobNotFoundError`` message maps to the generic ``Job not found`` (see
:func:`src.api.errors.error_mapping._normalized_job_not_found_detail`).
``BENCHMARK_COMPARE_JOBS_MUST_DIFFER`` and ``ANALYTICS_SCOPE_VALIDATION_FAILED`` use single
canonical ``detail`` strings aligned with their sole use-case emitters (not ``str(exc)``).

**Transition:** for structured errors, ``code`` is the stable machine identifier; ``detail`` is
the human-facing string (fixed for Category A, templated for structured Category B). New
clients should branch on ``code``; existing clients may keep reading ``detail`` only.

Broader plain ``HTTPException`` defaults are unchanged for compatibility.
"""

from __future__ import annotations

from fastapi import HTTPException

# ---------------------------------------------------------------------------
# Stable error ``code`` catalog (v3 JSON body: ``{"code", "detail"}``)
# ---------------------------------------------------------------------------
# Rules: UPPER_SNAKE_CASE; one business concept per constant; prefer domain nouns over
# transport words (avoid ``HTTP_404``). Add a constant only when :func:`mapped_http_exception`
# or a route intentionally raises :class:`StructuredApiHttpError` — then add contract tests.
# Do not fork near-duplicates: extend an existing code only with an explicit API note.
#
# Catalog groups (for maintainers; not an enum wire contract):
#   Not-found (Category A): INVENTORY_*, AISLE_*, POSITION_*, PRODUCT_*, VISUAL_REFERENCE_*, ASSET_*.
#   Jobs / scope / conflict (structured Category B): JOB_*, ACTIVE_JOB_*, JOB_PROMOTION_*.
#   Analytics / benchmark: BENCHMARK_COMPARE_*, ANALYTICS_SCOPE_*.
#   Infrastructure: INTERNAL_SERVER_ERROR (global unhandled path).

INVENTORY_NOT_FOUND = "INVENTORY_NOT_FOUND"
AISLE_NOT_FOUND = "AISLE_NOT_FOUND"
POSITION_NOT_FOUND = "POSITION_NOT_FOUND"
PRODUCT_NOT_FOUND = "PRODUCT_NOT_FOUND"
VISUAL_REFERENCE_NOT_FOUND = "VISUAL_REFERENCE_NOT_FOUND"
ASSET_NOT_FOUND = "ASSET_NOT_FOUND"
INTERNAL_SERVER_ERROR = "INTERNAL_SERVER_ERROR"
JOB_NOT_FOUND = "JOB_NOT_FOUND"
JOB_NOT_IN_AISLE_SCOPE = "JOB_NOT_IN_AISLE_SCOPE"
ACTIVE_JOB_EXISTS = "ACTIVE_JOB_EXISTS"
AISLE_SOURCE_ASSET_MUTATION_BLOCKED = "AISLE_SOURCE_ASSET_MUTATION_BLOCKED"
JOB_PROMOTION_NOT_ALLOWED = "JOB_PROMOTION_NOT_ALLOWED"
BENCHMARK_COMPARE_JOBS_MUST_DIFFER = "BENCHMARK_COMPARE_JOBS_MUST_DIFFER"
BENCHMARK_COMPARE_MANY_INVALID_SELECTION = "BENCHMARK_COMPARE_MANY_INVALID_SELECTION"
ANALYTICS_SCOPE_VALIDATION_FAILED = "ANALYTICS_SCOPE_VALIDATION_FAILED"
AISLE_HAS_NO_SOURCE_ASSETS_FOR_PROCESSING = "AISLE_HAS_NO_SOURCE_ASSETS_FOR_PROCESSING"
EMPTY_UPLOAD = "EMPTY_UPLOAD"
ZERO_BYTE_FILE = "ZERO_BYTE_FILE"
UNSUPPORTED_ASSET_TYPE = "UNSUPPORTED_ASSET_TYPE"
CAPTURE_SESSION_NOT_FOUND = "CAPTURE_SESSION_NOT_FOUND"
OPEN_CAPTURE_SESSION_EXISTS = "OPEN_CAPTURE_SESSION_EXISTS"
CAPTURE_SESSION_INVALID_STATE = "CAPTURE_SESSION_INVALID_STATE"
CAPTURE_SESSION_NOT_ACCEPTING_UPLOADS = "CAPTURE_SESSION_NOT_ACCEPTING_UPLOADS"
CAPTURE_SESSION_DUPLICATE_ITEM_CONTENT = "CAPTURE_SESSION_DUPLICATE_ITEM_CONTENT"
CAPTURE_SESSION_UPLOAD_BATCH_TOO_LARGE = "CAPTURE_SESSION_UPLOAD_BATCH_TOO_LARGE"
CAPTURE_SESSION_STAGING_FILE_TOO_LARGE = "CAPTURE_SESSION_STAGING_FILE_TOO_LARGE"
CAPTURE_SESSION_STATUS_FILTER_INVALID = "CAPTURE_SESSION_STATUS_FILTER_INVALID"
CAPTURE_SESSION_INVALID_CLOCK_OFFSET = "CAPTURE_SESSION_INVALID_CLOCK_OFFSET"
CAPTURE_SESSION_PREVIEW_NOT_ALLOWED = "CAPTURE_SESSION_PREVIEW_NOT_ALLOWED"


class StructuredApiHttpError(HTTPException):
    """HTTP error serialized as ``{"code": "<error_code>", "detail": "<detail>"}``.

    Subclasses Starlette/FastAPI :class:`HTTPException` so call sites and ``pytest.raises``
    patterns remain valid; a dedicated exception handler emits the flat JSON shape.
    """

    def __init__(self, status_code: int, *, error_code: str, detail: str) -> None:
        self.error_code = error_code
        super().__init__(status_code=status_code, detail=detail)
