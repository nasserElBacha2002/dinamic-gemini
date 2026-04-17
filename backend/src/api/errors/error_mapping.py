"""Central mapping from application-layer exceptions to :class:`fastapi.HTTPException`.

Routes should prefer :func:`mapped_http_exception` for known errors and re-raise unmapped
exceptions so the global handler can produce a safe 500 response.
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
    """Return an HTTPException for known mapped errors, or ``None`` if not mapped.

    Intentionally excludes broad types such as :class:`ValueError`; routes keep explicit
    handling where validation semantics differ (400 vs 422 vs 409).
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

    Logs unexpected failures at exception level without echoing internal text to the client.
    Optional ``log_context`` keys (e.g. ``inventory_id``, ``aisle_id``, ``position_id``) are
    appended to the log message when provided.
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
