"""Central mapping from application-layer exceptions to :class:`fastapi.HTTPException`.

Routes should prefer :func:`mapped_http_exception` / :func:`reraise_if_mapped` for known
errors and re-raise unmapped exceptions so the global handler can produce a safe 500 response.

--------------------------------------------------------------------
v3 API error **response contract** (normative for this package)
--------------------------------------------------------------------

Wire format stays FastAPI’s usual ``{"detail": ...}`` unless a dedicated exception handler
returns a different body (e.g. :class:`src.auth.errors.AuthHttpError`).

**Category A — stable fixed ``detail`` (preferred for *new* mappings)**  
Intentional public copy; do not change without an explicit API / client contract note:

- ``Inventory not found``
- ``Aisle not found or does not belong to this inventory``
- ``Position not found or does not belong to this aisle``
- ``Product not found or does not belong to this position``
- ``Visual reference not found``

**Additive ``code`` field (v3 rollout — partial, not universal)**  
:func:`mapped_http_exception` returns :class:`src.api.errors.structured_api_http.StructuredApiHttpError`
for:

- **Category A:** the five stable not-found rows above (fixed ``detail`` strings).
- **Category B (Phase 2 subset only):** ``JobNotFoundError``, ``JobDoesNotBelongToAisleError``,
  ``ActiveJobExistsError``, ``JobPromotionNotAllowedError`` — **``detail`` remains**
  ``str(exc)`` exactly as before (dynamic copy unchanged); only ``code`` is added.

The app serializes structured errors as
``{"code": "<UPPER_SNAKE_CASE>", "detail": "<string>"}``.

**Mixed responses across the API:** the same status code (e.g. 404) may return structured JSON
for mapper-covered types above, but **legacy** ``{"detail": ...}`` for other failures (artifacts,
most remaining Category B branches, route-local Phase 6 job messages, validation, etc.).
**Never infer** client behavior from status code alone; do not assume ``code`` is always present.

Clients that only read ``detail`` remain compatible. Category C paths and **unselected**
Category B branches stay plain ``HTTPException`` until a later phase.

:class:`StoredArtifactAccessError` is **A-like** in spirit: ``status_code`` and ``detail``
are set by the artifact layer per failure reason (not raw stack traces). It remains
``detail``-only JSON (no ``code`` in this phase).

**Category B — compatibility-preserved ``detail=str(exc)``**  
Most branches keep plain ``HTTPException`` with dynamic text. A **small Phase 2 subset** also
returns :class:`src.api.errors.structured_api_http.StructuredApiHttpError` with the **same**
``detail=str(exc)`` as before — additive ``code`` only; do not normalize messages here
(Phase 3+). **Do not extend** structured Category B without the same bar: clear semantics,
multi-route use, and explicit API review.

**Category C — route-local ``HTTPException`` only**  
Some routes **must not** use the mapper alone when a **different** fixed string is required
for regression tests, UX, or reduced information disclosure (e.g. Phase 6 job read helpers
that return ``"Job not found"`` without echoing the underlying ``JobNotFoundError`` message).
Keep those translations in the route (or a small helper) and document *why* in that helper.

**Known dual-shape (same ``detail`` string, different JSON):**  
``src.api.routes.v3.aisles._load_job_for_inventory_job_route`` catches ``AisleNotFoundError`` and
raises plain ``HTTPException`` with the **same** fixed ``detail`` as the Category A aisle branch,
but **without** ``code`` — intentional Category C behavior for job-scoped reads (see that
helper's docstring). Do not “fix” by routing through :func:`reraise_if_mapped` without an
explicit API contract change.

**Equivalence**  
Equivalent inventory/aisle/position/analytics flows should rely on the same mapper branch
for the same exception class. If two endpoints diverge, treat it as a bug **unless** one
side is intentionally **Category C**.

**Unexpected failures**  
Never return arbitrary internal ``str(exc)`` for unhandled errors; use
:func:`src.api.server.unhandled_exception_handler` or a fixed safe ``detail`` (see
:func:`review_exception_to_http` for review POST).

--------------------------------------------------------------------
Broad builtins (e.g. ``ValueError``)
--------------------------------------------------------------------

``ValueError`` is **not** mapped here: different routes use 400 / 422 / 409 for the same
Python type. Routes and :func:`review_exception_to_http` keep explicit handling.

**When to add a new type to** :func:`mapped_http_exception`

- Add a **narrow, domain-specific** exception class when **multiple routes** already map
  it the same way, or a new cross-cutting error must stay consistent.
- Preserve **status + detail** contracts unless the team intentionally changes API behavior.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException

from src.application.errors import (
    ActiveJobExistsError,
    AisleNotFoundError,
    AnalyticsScopeValidationError,
    BenchmarkCompareJobsMustDifferError,
    BenchmarkRequiresTestInventoryError,
    DuplicateAisleCodeError,
    EmptyUploadError,
    InventoryNotFoundError,
    InventoryVisualReferenceNotFoundError,
    InvalidProcessingModelError,
    InvalidProcessingPromptKeyError,
    JobDoesNotBelongToAisleError,
    JobNotFoundError,
    JobPromotionNotAllowedError,
    MaxInventoryVisualReferencesExceededError,
    MergeJobScopeAmbiguousError,
    PositionDeletedError,
    PositionNotFoundError,
    PositionResultContextMismatchError,
    ProcessingProviderNotConfiguredError,
    ProductNotFoundError,
    ReviewMutationNotAllowedError,
    UnknownProcessingProviderError,
    UnsupportedAssetTypeError,
    ZeroByteFileError,
)
from src.api.errors.structured_api_http import (
    ACTIVE_JOB_EXISTS,
    AISLE_NOT_FOUND,
    INVENTORY_NOT_FOUND,
    JOB_NOT_FOUND,
    JOB_NOT_IN_AISLE_SCOPE,
    JOB_PROMOTION_NOT_ALLOWED,
    POSITION_NOT_FOUND,
    PRODUCT_NOT_FOUND,
    VISUAL_REFERENCE_NOT_FOUND,
    StructuredApiHttpError,
)
from src.api.services.v3_stored_artifact_access import StoredArtifactAccessError

logger = logging.getLogger(__name__)

# Client-safe message for failures that are not mapped to a business rule.
_UNHANDLED_REVIEW_DETAIL = "An unexpected error occurred while processing this request."


def mapped_http_exception(exc: BaseException) -> HTTPException | None:
    """Return an ``HTTPException`` for registered errors, or ``None`` if not handled here.

    Returns ``None`` for any exception type not explicitly listed below—including
    :class:`ValueError` and other broad builtins—so callers can apply route-specific rules
    or fall through to the global unexpected-error handler.

    Do **not** extend this function with ``ValueError`` (see module docstring): status and
    detail for value-level validation differ by endpoint and must stay explicit at the route
    or use-case boundary.
    """
    # StoredArtifactAccessError: Category A (reason-curated detail, not traceback text).
    if isinstance(exc, StoredArtifactAccessError):
        return HTTPException(status_code=exc.status_code, detail=exc.detail)
    # --- Category A: stable fixed-detail not-found / scope errors (+ additive error codes) ---
    if isinstance(exc, InventoryNotFoundError):
        return StructuredApiHttpError(
            404,
            error_code=INVENTORY_NOT_FOUND,
            detail="Inventory not found",
        )
    if isinstance(exc, AisleNotFoundError):
        return StructuredApiHttpError(
            404,
            error_code=AISLE_NOT_FOUND,
            detail="Aisle not found or does not belong to this inventory",
        )
    if isinstance(exc, PositionNotFoundError):
        return StructuredApiHttpError(
            404,
            error_code=POSITION_NOT_FOUND,
            detail="Position not found or does not belong to this aisle",
        )
    if isinstance(exc, ProductNotFoundError):
        return StructuredApiHttpError(
            404,
            error_code=PRODUCT_NOT_FOUND,
            detail="Product not found or does not belong to this position",
        )
    if isinstance(exc, InventoryVisualReferenceNotFoundError):
        return StructuredApiHttpError(
            404,
            error_code=VISUAL_REFERENCE_NOT_FOUND,
            detail="Visual reference not found",
        )
    # --- Category B (Phase 2): dynamic detail=str(exc) + additive machine code ---
    if isinstance(exc, JobNotFoundError):
        return StructuredApiHttpError(
            status_code=404,
            error_code=JOB_NOT_FOUND,
            detail=str(exc),
        )
    if isinstance(exc, JobDoesNotBelongToAisleError):
        return StructuredApiHttpError(
            status_code=404,
            error_code=JOB_NOT_IN_AISLE_SCOPE,
            detail=str(exc),
        )
    if isinstance(exc, PositionResultContextMismatchError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, PositionDeletedError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, DuplicateAisleCodeError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, ActiveJobExistsError):
        return StructuredApiHttpError(
            status_code=409,
            error_code=ACTIVE_JOB_EXISTS,
            detail=str(exc),
        )
    if isinstance(exc, BenchmarkRequiresTestInventoryError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, JobPromotionNotAllowedError):
        return StructuredApiHttpError(
            status_code=409,
            error_code=JOB_PROMOTION_NOT_ALLOWED,
            detail=str(exc),
        )
    if isinstance(exc, ReviewMutationNotAllowedError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, EmptyUploadError):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, ZeroByteFileError):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, UnknownProcessingProviderError):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, InvalidProcessingModelError):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, InvalidProcessingPromptKeyError):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, ProcessingProviderNotConfiguredError):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, BenchmarkCompareJobsMustDifferError):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, MergeJobScopeAmbiguousError):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, AnalyticsScopeValidationError):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, UnsupportedAssetTypeError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, MaxInventoryVisualReferencesExceededError):
        return HTTPException(status_code=400, detail=str(exc))
    return None


def reraise_if_mapped(exc: BaseException, *, cause: BaseException | None = None) -> None:
    """If ``exc`` is covered by :func:`mapped_http_exception`, raise the mapped exception.

    The raised value is always a :class:`fastapi.HTTPException` **subclass** — either
    plain :class:`fastapi.HTTPException` (unstructured mapper branches, Category C, etc.) or
    :class:`src.api.errors.structured_api_http.StructuredApiHttpError` (Category A, selected
    Category B job/conflict types — see module docstring).
    Call sites and ``pytest.raises(HTTPException)`` remain valid because
    ``StructuredApiHttpError`` extends ``HTTPException``; use
    ``pytest.raises(StructuredApiHttpError)`` when asserting ``error_code``.

    If there is no mapping, return without raising so the caller can apply route-specific
    rules (for example ``ValueError`` with 422 vs 409) or re-raise the original error.

    When ``cause`` is set, the raised exception uses ``raise ... from cause`` so exception
    chaining is preserved in logs.
    """
    m = mapped_http_exception(exc)
    if m is None:
        return
    if cause is not None:
        raise m from cause
    raise m


def review_exception_to_http(exc: Exception, **log_context: Any) -> HTTPException:
    """Map review use-case exceptions to HTTP; unknown errors become a safe 500-shaped response.

    :class:`ValueError` is handled **here** (422 + ``str(exc)``) for the review POST surface,
    not in :func:`mapped_http_exception`—see module docstring for why ``ValueError`` is not
    in the shared mapper.

    Logs unexpected failures at exception level without echoing internal text to the client.
    Optional ``log_context`` keys (e.g. ``inventory_id``, ``aisle_id``, ``position_id``,
    ``job_id``) are appended to the log message when provided (non-``None`` values only).
    """
    mapped = mapped_http_exception(exc)
    if mapped is not None:
        return mapped
    if isinstance(exc, ValueError):
        return HTTPException(status_code=422, detail=str(exc))
    ctx = {k: v for k, v in log_context.items() if v is not None}
    suffix = (" context=%r" % (ctx,)) if ctx else ""
    logger.exception("Unhandled exception while mapping review error to HTTP%s", suffix)
    return HTTPException(status_code=500, detail=_UNHANDLED_REVIEW_DETAIL)
