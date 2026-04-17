"""Central mapping from application-layer exceptions to :class:`fastapi.HTTPException`.

Routes should prefer :func:`mapped_http_exception` for known errors and re-raise unmapped
exceptions so the global handler can produce a safe 500 response.

**Intentionally out of scope for** :func:`mapped_http_exception` **— broad** ``ValueError``

``ValueError`` is **not** mapped here on purpose. Different routes attach different HTTP
semantics to the same failure shape (400 vs 422 vs 409). Centralizing ``ValueError`` in
this module would invite wrong status codes or accidental contract drift. Routes (and
review-specific helpers such as :func:`review_exception_to_http`) keep explicit handling
for validation-style ``ValueError`` where the contract is already defined.

**When to add a new type to** :func:`mapped_http_exception`

- Add a **narrow, domain-specific** exception class (typically from
  ``src.application.errors`` or a dedicated API error like ``StoredArtifactAccessError``)
  when **multiple routes** already map it the same way, or you are introducing a new
  cross-cutting error that should stay consistent everywhere.
- Keep **route-local** ``HTTPException`` translation when semantics are one-off, depend on
  request shape, or differ by verb/path.
- Preserve existing response **status + detail** contracts unless the team intentionally
  changes API behavior; do not "improve" messages in the mapper without a compatibility plan.
- For **unexpected** failures, never surface raw internal trace or arbitrary ``str(exc)`` to
  clients; use the global handler or a fixed safe ``detail`` string.

**``str(exc)`` in this module:** several branches keep ``detail=str(exc)`` **only** because
existing clients already rely on that dynamic text. **New** mappings should prefer stable,
operator-safe fixed strings unless a route already depends on message-level detail.
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
    if isinstance(exc, StoredArtifactAccessError):
        return HTTPException(status_code=exc.status_code, detail=exc.detail)
    if isinstance(exc, InventoryNotFoundError):
        return HTTPException(status_code=404, detail="Inventory not found")
    if isinstance(exc, AisleNotFoundError):
        return HTTPException(status_code=404, detail="Aisle not found or does not belong to this inventory")
    if isinstance(exc, PositionNotFoundError):
        return HTTPException(status_code=404, detail="Position not found or does not belong to this aisle")
    if isinstance(exc, ProductNotFoundError):
        return HTTPException(status_code=404, detail="Product not found or does not belong to this position")
    if isinstance(exc, InventoryVisualReferenceNotFoundError):
        return HTTPException(status_code=404, detail="Visual reference not found")
    # --- detail=str(exc): preserved for backward compatibility with existing API clients ---
    if isinstance(exc, JobNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, JobDoesNotBelongToAisleError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, PositionResultContextMismatchError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, PositionDeletedError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, DuplicateAisleCodeError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, ActiveJobExistsError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, BenchmarkRequiresTestInventoryError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, JobPromotionNotAllowedError):
        return HTTPException(status_code=409, detail=str(exc))
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
