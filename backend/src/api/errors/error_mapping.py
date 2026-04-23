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
- **Category B (structured subset):** ``JobNotFoundError``, ``JobDoesNotBelongToAisleError``,
  ``ActiveJobExistsError``, ``JobPromotionNotAllowedError``, ``BenchmarkCompareJobsMustDifferError``,
  ``AnalyticsScopeValidationError`` — **Phase 3:** public ``detail`` is
  built from **vetted templates** in this module (see ``_normalized_*`` helpers). In particular,
  ``JobNotFoundError``: if ``str(exc)`` matches the canonical ``Job not found: <id>`` pattern, that
  controlled detail (including the id) is preserved; **any other** message shape collapses to the
  stable generic ``Job not found`` so arbitrary free-form ``str(exc)`` is not part of the HTTP
  contract. ``BenchmarkCompareJobsMustDifferError`` / ``AnalyticsScopeValidationError`` use one
  fixed public ``detail`` each (aligned with their use cases). Other structured job/conflict types
  use regex-backed templates where matched; see each helper for non-matching fallback (all
  current ``JobDoesNotBelongToAisleError`` raise sites match the two vetted patterns; unknown
  shapes collapse to a stable generic — see ``_normalized_job_does_not_belong_detail``).

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

**Category B — structured subset vs legacy branches**  
Most Category B types remain plain ``HTTPException`` with ``detail=str(exc)``. The **structured
job/conflict subset** (see above) uses controlled ``detail`` strings built in the mapper
(Phase 3). **Do not extend** structured Category B without: clear semantics, multi-route use,
documented templates, tests, and API review.

**``str(exc)`` deprecation (transitional):**  
Treating raw exception text as the HTTP contract is **legacy**. New domain errors should use
fixed or templated ``detail`` plus ``code`` (Category A pattern) or a vetted Category B template.
Remaining mapper branches still use ``str(exc)`` until a later phase migrates them.

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

**Known dual-shape (same *exception class*, different JSON — CRITICAL):**  
``JobNotFoundError`` (and ``JobDoesNotBelongToAisleError``) raised inside use cases and handled
via ``except Exception: reraise_if_mapped`` produce **structured** bodies (``code`` + controlled
``detail``). The **same** Python types caught earlier in ``_load_job_for_inventory_job_route``
never reach the mapper: that helper translates them into Category C ``HTTPException`` with
fixed phrases (e.g. ``"Job not found"``) and **no** ``code``. **Mapping path determines wire shape**
— do not assume one ``JobNotFoundError`` always implies structured JSON.

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

--------------------------------------------------------------------
Final v3 target contract (operating model)
--------------------------------------------------------------------

**Structured (default for mapped business rules in this module):** responses use
``{"code": "<STABLE_CODE>", "detail": "<controlled human text>"}`` via
:class:`src.api.errors.structured_api_http.StructuredApiHttpError` and the app handler.
``code`` is the machine identifier; ``detail`` is for display — clients must not parse
``detail`` for branching logic.

**Intentionally legacy (narrow, documented):**

1. **FastAPI / Pydantic validation** — ``{"detail": [<field errors>]}`` (framework-native).
2. **Auth** — ``{"error": {"code", "message"}}`` (separate product contract).
3. **Category C** — selected aisle job-read helpers: fixed ``detail`` only, no ``code`` (Phase 6
   regression / disclosure policy); see ``aisles._load_job_for_inventory_job_route``.
4. **``StoredArtifactAccessError``** — ``detail``-only via plain ``HTTPException`` (artifact
   layer owns copy; structuring deferred).
5. **Remaining mapper branches** still on ``HTTPException`` + ``str(exc)`` — see *Deferred
   structuring* below.

**Observability:** structured responses log ``error_code`` + path at INFO in
:func:`src.api.server.structured_api_http_error_handler`; unexpected failures use
``logger.exception`` in the global 500 handler.

**Deferred structuring (explicit backlog):** map to ``StructuredApiHttpError`` only after
templates + tests per type: ``PositionResultContextMismatchError``, ``PositionDeletedError``,
``DuplicateAisleCodeError``, ``BenchmarkRequiresTestInventoryError``, ``ReviewMutationNotAllowedError``,
``EmptyUploadError``, ``ZeroByteFileError``, ``UnknownProcessingProviderError``,
``InvalidProcessingModelError``, ``InvalidProcessingPromptKeyError``,
``ProcessingProviderNotConfiguredError``, ``MergeJobScopeAmbiguousError``,
``UnsupportedAssetTypeError``, ``MaxInventoryVisualReferencesExceededError``,
``StoredArtifactAccessError``. Broad ``ValueError`` stays route-local.

**When adding a new route:** prefer ``reraise_if_mapped`` for domain exceptions already in this
module; do not invent new English ``detail`` strings when a ``code`` + existing template applies;
never expose raw ``str(exc)`` on new paths.

**When to add a new type to** :func:`mapped_http_exception`

- Add a **narrow, domain-specific** exception class when **multiple routes** already map
  it the same way, or a new cross-cutting error must stay consistent.
- Preserve **status + detail** contracts unless the team intentionally changes API behavior.
- Assign a **stable** ``error_code`` constant; define **Category** (A fixed copy / B templated /
  C route-only); add **tests** for status, ``code``, and ``detail``; document any intentional
  divergence from other routes handling the same exception class.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from fastapi import HTTPException

from src.application.errors import (
    ActiveJobExistsError,
    AisleNotFoundError,
    AisleSourceAssetMutationBlockedError,
    AnalyticsScopeValidationError,
    BenchmarkCompareJobsMustDifferError,
    BenchmarkCompareManyInvalidSelectionError,
    BenchmarkRequiresTestInventoryError,
    CaptureSessionDuplicateItemContentError,
    AisleNotFoundForAssignmentError,
    CaptureSessionGroupAlreadyAssignedError,
    CaptureSessionGroupAssignmentNotAllowedError,
    CaptureSessionGroupNotFoundError,
    CaptureSessionGroupNotAssignedForMaterializationError,
    CaptureSessionGroupingNotAllowedError,
    CaptureSessionNoItemsForGroupingError,
    CaptureSessionInvalidClockOffsetError,
    CaptureSessionInvalidIdempotencyKeyError,
    CaptureSessionInvalidStateError,
    CaptureSessionMaterializationFailedError,
    CaptureSessionMaterializationNotAllowedError,
    CaptureSessionNotAcceptingUploadsError,
    CaptureSessionAlreadyMaterializedError,
    CaptureSessionNotFoundError,
    CaptureSessionPreviewNotAllowedError,
    CaptureSessionStagingFileTooLargeError,
    CaptureSessionStatusFilterInvalidError,
    CaptureSessionUploadBatchTooLargeError,
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
    NoSourceAssetsForAisleProcessingError,
    OpenCaptureSessionExistsError,
    PositionDeletedError,
    PositionNotFoundError,
    PositionResultContextMismatchError,
    ProcessingProviderNotConfiguredError,
    ProductNotFoundError,
    ReviewMutationNotAllowedError,
    SourceAssetNotFoundForAisleError,
    UnknownProcessingProviderError,
    UnsupportedAssetTypeError,
    ZeroByteFileError,
)
from src.api.constants.error_wire import (
    HTTP_DETAIL_AISLE_SOURCE_ASSETS_ACTIVE_JOB_BLOCKS_MUTATION,
    HTTP_DETAIL_AISLE_NO_SOURCE_ASSETS_FOR_PROCESSING,
    HTTP_DETAIL_ANALYTICS_SCOPE_VALIDATION_FAILED,
    HTTP_DETAIL_AISLE_NOT_FOUND_IN_INVENTORY,
    HTTP_DETAIL_BENCHMARK_COMPARE_JOBS_MUST_DIFFER,
    HTTP_DETAIL_AT_LEAST_ONE_FILE_REQUIRED,
    HTTP_DETAIL_EMPTY_OR_ZERO_BYTE_FILES_NOT_ALLOWED,
    HTTP_DETAIL_CAPTURE_SESSION_DUPLICATE_CONTENT,
    HTTP_DETAIL_CAPTURE_SESSION_FILE_TOO_LARGE,
    HTTP_DETAIL_CAPTURE_SESSION_STATUS_FILTER_INVALID,
    HTTP_DETAIL_CAPTURE_SESSION_INVALID_STATE,
    HTTP_DETAIL_CAPTURE_SESSION_INVALID_IDEMPOTENCY_KEY,
    HTTP_DETAIL_CAPTURE_SESSION_GROUPING_NOT_ALLOWED,
    HTTP_DETAIL_CAPTURE_SESSION_GROUP_ALREADY_ASSIGNED,
    HTTP_DETAIL_CAPTURE_SESSION_GROUP_ASSIGNMENT_NOT_ALLOWED,
    HTTP_DETAIL_CAPTURE_SESSION_GROUP_NOT_FOUND,
    HTTP_DETAIL_CAPTURE_SESSION_GROUP_NOT_ASSIGNED_FOR_MATERIALIZATION,
    HTTP_DETAIL_CAPTURE_SESSION_NO_ITEMS_FOR_GROUPING,
    HTTP_DETAIL_AISLE_NOT_FOUND_FOR_ASSIGNMENT,
    HTTP_DETAIL_CAPTURE_SESSION_NOT_ACCEPTING_UPLOADS,
    HTTP_DETAIL_CAPTURE_SESSION_MATERIALIZATION_NOT_ALLOWED,
    HTTP_DETAIL_CAPTURE_SESSION_MATERIALIZATION_FAILED,
    HTTP_DETAIL_CAPTURE_SESSION_ALREADY_MATERIALIZED,
    HTTP_DETAIL_CAPTURE_SESSION_NOT_FOUND,
    HTTP_DETAIL_CAPTURE_SESSION_UPLOAD_BATCH_TOO_LARGE,
    HTTP_DETAIL_INVENTORY_NOT_FOUND,
    HTTP_DETAIL_JOB_NOT_FOUND,
    HTTP_DETAIL_OPEN_CAPTURE_SESSION_EXISTS,
    HTTP_DETAIL_POSITION_NOT_FOUND_IN_AISLE,
    HTTP_DETAIL_PRODUCT_NOT_FOUND_ON_POSITION,
    HTTP_DETAIL_UNEXPECTED_ERROR,
    HTTP_DETAIL_VISUAL_REFERENCE_NOT_FOUND,
    HTTP_DETAIL_ASSET_NOT_FOUND,
)
from src.api.errors.structured_api_http import (
    ACTIVE_JOB_EXISTS,
    AISLE_NOT_FOUND,
    AISLE_SOURCE_ASSET_MUTATION_BLOCKED,
    ASSET_NOT_FOUND,
    AISLE_HAS_NO_SOURCE_ASSETS_FOR_PROCESSING,
    ANALYTICS_SCOPE_VALIDATION_FAILED,
    BENCHMARK_COMPARE_JOBS_MUST_DIFFER,
    BENCHMARK_COMPARE_MANY_INVALID_SELECTION,
    EMPTY_UPLOAD,
    UNSUPPORTED_ASSET_TYPE,
    ZERO_BYTE_FILE,
    CAPTURE_SESSION_DUPLICATE_ITEM_CONTENT,
    AISLE_NOT_FOUND_FOR_ASSIGNMENT,
    CAPTURE_SESSION_GROUP_ALREADY_ASSIGNED,
    CAPTURE_SESSION_GROUP_ASSIGNMENT_NOT_ALLOWED,
    CAPTURE_SESSION_GROUP_NOT_FOUND,
    CAPTURE_SESSION_GROUP_NOT_ASSIGNED_FOR_MATERIALIZATION,
    CAPTURE_SESSION_GROUPING_NOT_ALLOWED,
    CAPTURE_SESSION_NO_ITEMS_FOR_GROUPING,
    CAPTURE_SESSION_INVALID_CLOCK_OFFSET,
    CAPTURE_SESSION_INVALID_IDEMPOTENCY_KEY,
    CAPTURE_SESSION_INVALID_STATE,
    CAPTURE_SESSION_NOT_ACCEPTING_UPLOADS,
    CAPTURE_SESSION_NOT_FOUND,
    CAPTURE_SESSION_PREVIEW_NOT_ALLOWED,
    CAPTURE_SESSION_MATERIALIZATION_NOT_ALLOWED,
    CAPTURE_SESSION_MATERIALIZATION_FAILED,
    CAPTURE_SESSION_ALREADY_MATERIALIZED,
    CAPTURE_SESSION_STAGING_FILE_TOO_LARGE,
    CAPTURE_SESSION_STATUS_FILTER_INVALID,
    CAPTURE_SESSION_UPLOAD_BATCH_TOO_LARGE,
    INTERNAL_SERVER_ERROR,
    INVENTORY_NOT_FOUND,
    JOB_NOT_FOUND,
    JOB_NOT_IN_AISLE_SCOPE,
    JOB_PROMOTION_NOT_ALLOWED,
    OPEN_CAPTURE_SESSION_EXISTS,
    POSITION_NOT_FOUND,
    PRODUCT_NOT_FOUND,
    VISUAL_REFERENCE_NOT_FOUND,
    StructuredApiHttpError,
)
from src.api.services.v3_stored_artifact_access import StoredArtifactAccessError

logger = logging.getLogger(__name__)

# --- Phase 3: controlled ``detail`` for structured Category B (known use-case shapes only) ---
_JOB_NOT_FOUND_CANON = re.compile(r"^Job not found: (.+)$")
_JOB_SCOPE_NOT_SCOPED = re.compile(r"^Job (.+?) is not scoped to aisle (.+)$")
_JOB_SCOPE_DOES_NOT_BELONG = re.compile(r"^Job (.+?) does not belong to aisle (.+)$")
_ACTIVE_JOB_EXISTS = re.compile(r"^Aisle (.+?) already has an active job \(status=(.+)\)$")
_JOB_PROMOTE_TYPE = re.compile(r"^Only process_aisle jobs can be promoted \(got (.+)\)$")
_JOB_PROMOTE_STATUS = re.compile(r"^Only succeeded jobs can be promoted \(status=(.+)\)$")

def _normalized_job_not_found_detail(exc: JobNotFoundError) -> str:
    """Phase 3 ``JobNotFoundError`` → HTTP ``detail`` (mapper-only; Category C routes unchanged).

    - **Canonical:** ``str(exc)`` matches ``^Job not found: (.+)$`` (use-case convention). The
      public detail stays ``Job not found: <id>`` — controlled dynamic segment, not arbitrary text.
    - **Non-canonical / free-form:** any other ``str(exc)`` collapses to the stable generic
      ``Job not found``. Intentional: ``code`` carries the machine case; ``detail`` must not echo
      unvetted exception copy.
    """
    raw = str(exc).strip()
    m = _JOB_NOT_FOUND_CANON.match(raw)
    if m:
        return f"{HTTP_DETAIL_JOB_NOT_FOUND}: {m.group(1)}"
    return HTTP_DETAIL_JOB_NOT_FOUND


def _normalized_job_does_not_belong_detail(exc: JobDoesNotBelongToAisleError) -> str:
    """``JobDoesNotBelongToAisleError`` → HTTP ``detail`` (mapper path only; Category C unchanged).

    **Known patterns (all current raise sites in ``application/`` match one of these):**

    1. ``Job <job_id> is not scoped to aisle <aisle_id>`` — resolve / compare / export / promote.
    2. ``Job <job_id> does not belong to aisle <aisle_id>`` — result context resolver, merge
       recompute (legacy wording).

    Both normalize to the same public template: ``Job <job_id> is not scoped to aisle <aisle_id>``.

    **Unknown / free-form:** if ``str(exc)`` matches neither pattern (tests or future code), return
    the stable generic ``"Job is not scoped to this aisle"`` — same policy as other structured
    Category B fallbacks: never echo arbitrary ``str(exc)``; clients use ``JOB_NOT_IN_AISLE_SCOPE``
    for branching and may use ``detail`` when it includes ids.
    """
    raw = str(exc).strip()
    m = _JOB_SCOPE_NOT_SCOPED.match(raw)
    if m:
        return f"Job {m.group(1)} is not scoped to aisle {m.group(2)}"
    m = _JOB_SCOPE_DOES_NOT_BELONG.match(raw)
    if m:
        return f"Job {m.group(1)} is not scoped to aisle {m.group(2)}"
    return "Job is not scoped to this aisle"


def _normalized_active_job_exists_detail(exc: ActiveJobExistsError) -> str:
    raw = str(exc).strip()
    m = _ACTIVE_JOB_EXISTS.match(raw)
    if m:
        return f"Aisle {m.group(1)} already has an active job (status={m.group(2)})"
    return "An active job already exists for this aisle"


def _normalized_job_promotion_not_allowed_detail(exc: JobPromotionNotAllowedError) -> str:
    raw = str(exc).strip()
    m = _JOB_PROMOTE_TYPE.match(raw)
    if m:
        return f"Only process_aisle jobs can be promoted (got {m.group(1)})"
    m = _JOB_PROMOTE_STATUS.match(raw)
    if m:
        return f"Only succeeded jobs can be promoted (status={m.group(1)})"
    return "This job cannot be promoted to operational"


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
            detail=HTTP_DETAIL_INVENTORY_NOT_FOUND,
        )
    if isinstance(exc, AisleNotFoundError):
        return StructuredApiHttpError(
            404,
            error_code=AISLE_NOT_FOUND,
            detail=HTTP_DETAIL_AISLE_NOT_FOUND_IN_INVENTORY,
        )
    if isinstance(exc, PositionNotFoundError):
        return StructuredApiHttpError(
            404,
            error_code=POSITION_NOT_FOUND,
            detail=HTTP_DETAIL_POSITION_NOT_FOUND_IN_AISLE,
        )
    if isinstance(exc, ProductNotFoundError):
        return StructuredApiHttpError(
            404,
            error_code=PRODUCT_NOT_FOUND,
            detail=HTTP_DETAIL_PRODUCT_NOT_FOUND_ON_POSITION,
        )
    if isinstance(exc, InventoryVisualReferenceNotFoundError):
        return StructuredApiHttpError(
            404,
            error_code=VISUAL_REFERENCE_NOT_FOUND,
            detail=HTTP_DETAIL_VISUAL_REFERENCE_NOT_FOUND,
        )
    if isinstance(exc, SourceAssetNotFoundForAisleError):
        return StructuredApiHttpError(
            404,
            error_code=ASSET_NOT_FOUND,
            detail=HTTP_DETAIL_ASSET_NOT_FOUND,
        )
    # --- Category B (Phase 2–3): structured + controlled ``detail`` templates ---
    # ``JobNotFoundError``: canonical ``Job not found: <id>`` preserved; anything else → ``Job not found``.
    # See ``_normalized_job_not_found_detail`` (same rule as module docstring).
    if isinstance(exc, JobNotFoundError):
        return StructuredApiHttpError(
            status_code=404,
            error_code=JOB_NOT_FOUND,
            detail=_normalized_job_not_found_detail(exc),
        )
    if isinstance(exc, JobDoesNotBelongToAisleError):
        return StructuredApiHttpError(
            status_code=404,
            error_code=JOB_NOT_IN_AISLE_SCOPE,
            detail=_normalized_job_does_not_belong_detail(exc),
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
            detail=_normalized_active_job_exists_detail(exc),
        )
    if isinstance(exc, NoSourceAssetsForAisleProcessingError):
        return StructuredApiHttpError(
            status_code=409,
            error_code=AISLE_HAS_NO_SOURCE_ASSETS_FOR_PROCESSING,
            detail=HTTP_DETAIL_AISLE_NO_SOURCE_ASSETS_FOR_PROCESSING,
        )
    if isinstance(exc, AisleSourceAssetMutationBlockedError):
        return StructuredApiHttpError(
            status_code=409,
            error_code=AISLE_SOURCE_ASSET_MUTATION_BLOCKED,
            detail=HTTP_DETAIL_AISLE_SOURCE_ASSETS_ACTIVE_JOB_BLOCKS_MUTATION,
        )
    if isinstance(exc, BenchmarkRequiresTestInventoryError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, JobPromotionNotAllowedError):
        return StructuredApiHttpError(
            status_code=409,
            error_code=JOB_PROMOTION_NOT_ALLOWED,
            detail=_normalized_job_promotion_not_allowed_detail(exc),
        )
    if isinstance(exc, ReviewMutationNotAllowedError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, EmptyUploadError):
        return StructuredApiHttpError(
            status_code=422,
            error_code=EMPTY_UPLOAD,
            detail=HTTP_DETAIL_AT_LEAST_ONE_FILE_REQUIRED,
        )
    if isinstance(exc, ZeroByteFileError):
        return StructuredApiHttpError(
            status_code=422,
            error_code=ZERO_BYTE_FILE,
            detail=HTTP_DETAIL_EMPTY_OR_ZERO_BYTE_FILES_NOT_ALLOWED,
        )
    if isinstance(exc, UnknownProcessingProviderError):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, InvalidProcessingModelError):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, InvalidProcessingPromptKeyError):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, ProcessingProviderNotConfiguredError):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, BenchmarkCompareJobsMustDifferError):
        return StructuredApiHttpError(
            status_code=422,
            error_code=BENCHMARK_COMPARE_JOBS_MUST_DIFFER,
            detail=HTTP_DETAIL_BENCHMARK_COMPARE_JOBS_MUST_DIFFER,
        )
    if isinstance(exc, BenchmarkCompareManyInvalidSelectionError):
        return StructuredApiHttpError(
            status_code=422,
            error_code=BENCHMARK_COMPARE_MANY_INVALID_SELECTION,
            detail=str(exc),
        )
    if isinstance(exc, MergeJobScopeAmbiguousError):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, AnalyticsScopeValidationError):
        return StructuredApiHttpError(
            status_code=422,
            error_code=ANALYTICS_SCOPE_VALIDATION_FAILED,
            detail=HTTP_DETAIL_ANALYTICS_SCOPE_VALIDATION_FAILED,
        )
    if isinstance(exc, CaptureSessionNotFoundError):
        return StructuredApiHttpError(
            status_code=404,
            error_code=CAPTURE_SESSION_NOT_FOUND,
            detail=HTTP_DETAIL_CAPTURE_SESSION_NOT_FOUND,
        )
    if isinstance(exc, OpenCaptureSessionExistsError):
        return StructuredApiHttpError(
            status_code=409,
            error_code=OPEN_CAPTURE_SESSION_EXISTS,
            detail=HTTP_DETAIL_OPEN_CAPTURE_SESSION_EXISTS,
        )
    if isinstance(exc, CaptureSessionInvalidClockOffsetError):
        return StructuredApiHttpError(
            status_code=422,
            error_code=CAPTURE_SESSION_INVALID_CLOCK_OFFSET,
            detail=str(exc),
        )
    if isinstance(exc, CaptureSessionPreviewNotAllowedError):
        return StructuredApiHttpError(
            status_code=409,
            error_code=CAPTURE_SESSION_PREVIEW_NOT_ALLOWED,
            detail=str(exc),
        )
    if isinstance(exc, CaptureSessionGroupingNotAllowedError):
        return StructuredApiHttpError(
            status_code=409,
            error_code=CAPTURE_SESSION_GROUPING_NOT_ALLOWED,
            detail=str(exc) or HTTP_DETAIL_CAPTURE_SESSION_GROUPING_NOT_ALLOWED,
        )
    if isinstance(exc, CaptureSessionNoItemsForGroupingError):
        return StructuredApiHttpError(
            status_code=422,
            error_code=CAPTURE_SESSION_NO_ITEMS_FOR_GROUPING,
            detail=str(exc) or HTTP_DETAIL_CAPTURE_SESSION_NO_ITEMS_FOR_GROUPING,
        )
    if isinstance(exc, CaptureSessionGroupNotFoundError):
        return StructuredApiHttpError(
            status_code=404,
            error_code=CAPTURE_SESSION_GROUP_NOT_FOUND,
            detail=str(exc) or HTTP_DETAIL_CAPTURE_SESSION_GROUP_NOT_FOUND,
        )
    if isinstance(exc, CaptureSessionGroupNotAssignedForMaterializationError):
        return StructuredApiHttpError(
            status_code=422,
            error_code=CAPTURE_SESSION_GROUP_NOT_ASSIGNED_FOR_MATERIALIZATION,
            detail=str(exc) or HTTP_DETAIL_CAPTURE_SESSION_GROUP_NOT_ASSIGNED_FOR_MATERIALIZATION,
        )
    if isinstance(exc, CaptureSessionGroupAlreadyAssignedError):
        return StructuredApiHttpError(
            status_code=409,
            error_code=CAPTURE_SESSION_GROUP_ALREADY_ASSIGNED,
            detail=str(exc) or HTTP_DETAIL_CAPTURE_SESSION_GROUP_ALREADY_ASSIGNED,
        )
    if isinstance(exc, CaptureSessionGroupAssignmentNotAllowedError):
        return StructuredApiHttpError(
            status_code=409,
            error_code=CAPTURE_SESSION_GROUP_ASSIGNMENT_NOT_ALLOWED,
            detail=str(exc) or HTTP_DETAIL_CAPTURE_SESSION_GROUP_ASSIGNMENT_NOT_ALLOWED,
        )
    if isinstance(exc, AisleNotFoundForAssignmentError):
        return StructuredApiHttpError(
            status_code=404,
            error_code=AISLE_NOT_FOUND_FOR_ASSIGNMENT,
            detail=str(exc) or HTTP_DETAIL_AISLE_NOT_FOUND_FOR_ASSIGNMENT,
        )
    if isinstance(exc, CaptureSessionInvalidIdempotencyKeyError):
        return StructuredApiHttpError(
            status_code=422,
            error_code=CAPTURE_SESSION_INVALID_IDEMPOTENCY_KEY,
            detail=HTTP_DETAIL_CAPTURE_SESSION_INVALID_IDEMPOTENCY_KEY,
        )
    if isinstance(exc, CaptureSessionMaterializationNotAllowedError):
        return StructuredApiHttpError(
            status_code=409,
            error_code=CAPTURE_SESSION_MATERIALIZATION_NOT_ALLOWED,
            detail=HTTP_DETAIL_CAPTURE_SESSION_MATERIALIZATION_NOT_ALLOWED,
        )
    if isinstance(exc, CaptureSessionAlreadyMaterializedError):
        return StructuredApiHttpError(
            status_code=409,
            error_code=CAPTURE_SESSION_ALREADY_MATERIALIZED,
            detail=HTTP_DETAIL_CAPTURE_SESSION_ALREADY_MATERIALIZED,
        )
    if isinstance(exc, CaptureSessionMaterializationFailedError):
        return StructuredApiHttpError(
            status_code=500,
            error_code=CAPTURE_SESSION_MATERIALIZATION_FAILED,
            detail=HTTP_DETAIL_CAPTURE_SESSION_MATERIALIZATION_FAILED,
        )
    if isinstance(exc, CaptureSessionInvalidStateError):
        return StructuredApiHttpError(
            status_code=409,
            error_code=CAPTURE_SESSION_INVALID_STATE,
            detail=HTTP_DETAIL_CAPTURE_SESSION_INVALID_STATE,
        )
    if isinstance(exc, CaptureSessionNotAcceptingUploadsError):
        return StructuredApiHttpError(
            status_code=409,
            error_code=CAPTURE_SESSION_NOT_ACCEPTING_UPLOADS,
            detail=HTTP_DETAIL_CAPTURE_SESSION_NOT_ACCEPTING_UPLOADS,
        )
    if isinstance(exc, CaptureSessionDuplicateItemContentError):
        return StructuredApiHttpError(
            status_code=409,
            error_code=CAPTURE_SESSION_DUPLICATE_ITEM_CONTENT,
            detail=HTTP_DETAIL_CAPTURE_SESSION_DUPLICATE_CONTENT,
        )
    if isinstance(exc, CaptureSessionUploadBatchTooLargeError):
        return StructuredApiHttpError(
            status_code=422,
            error_code=CAPTURE_SESSION_UPLOAD_BATCH_TOO_LARGE,
            detail=HTTP_DETAIL_CAPTURE_SESSION_UPLOAD_BATCH_TOO_LARGE,
        )
    if isinstance(exc, CaptureSessionStagingFileTooLargeError):
        return StructuredApiHttpError(
            status_code=422,
            error_code=CAPTURE_SESSION_STAGING_FILE_TOO_LARGE,
            detail=HTTP_DETAIL_CAPTURE_SESSION_FILE_TOO_LARGE,
        )
    if isinstance(exc, CaptureSessionStatusFilterInvalidError):
        return StructuredApiHttpError(
            status_code=422,
            error_code=CAPTURE_SESSION_STATUS_FILTER_INVALID,
            detail=HTTP_DETAIL_CAPTURE_SESSION_STATUS_FILTER_INVALID,
        )
    if isinstance(exc, UnsupportedAssetTypeError):
        return StructuredApiHttpError(
            status_code=400,
            error_code=UNSUPPORTED_ASSET_TYPE,
            detail=str(exc),
        )
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

    Unknown failures return :class:`StructuredApiHttpError` with the same ``code`` + generic
    ``detail`` as :func:`src.api.server.unhandled_exception_handler` (aligned v3 500 contract).

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
    return StructuredApiHttpError(
        500,
        error_code=INTERNAL_SERVER_ERROR,
        detail=HTTP_DETAIL_UNEXPECTED_ERROR,
    )
