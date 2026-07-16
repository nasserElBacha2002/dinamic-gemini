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
``UnsupportedAssetTypeError``,
``StoredArtifactAccessError``. Broad ``ValueError`` stays route-local.

**When adding a new route:** prefer ``reraise_if_mapped`` for domain exceptions already in this
module; do not invent new English ``detail`` strings when a ``code`` + existing template applies;
never expose raw ``str(exc)`` on new paths.

**When to add a new type:** append an entry to ``_HTTP_EXCEPTION_DISPATCH`` (consumed by
:func:`mapped_http_exception`; same ordering rules as above).

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
from typing import Any, Callable, cast

from fastapi import HTTPException

from src.api.constants.error_wire import (
    HTTP_DETAIL_AISLE_INACTIVE,
    HTTP_DETAIL_AISLE_NO_SOURCE_ASSETS_FOR_CODE_SCAN,
    HTTP_DETAIL_AISLE_NO_SOURCE_ASSETS_FOR_PROCESSING,
    HTTP_DETAIL_AISLE_NOT_FOUND_FOR_ASSIGNMENT,
    HTTP_DETAIL_AISLE_NOT_FOUND_IN_INVENTORY,
    HTTP_DETAIL_AISLE_SOURCE_ASSETS_ACTIVE_JOB_BLOCKS_MUTATION,
    HTTP_DETAIL_ANALYTICS_SCOPE_VALIDATION_FAILED,
    HTTP_DETAIL_ASSET_NOT_FOUND,
    HTTP_DETAIL_AT_LEAST_ONE_FILE_REQUIRED,
    HTTP_DETAIL_BENCHMARK_COMPARE_JOBS_MUST_DIFFER,
    HTTP_DETAIL_CAPTURE_SESSION_ALREADY_MATERIALIZED,
    HTTP_DETAIL_CAPTURE_SESSION_DUPLICATE_CONTENT,
    HTTP_DETAIL_CAPTURE_SESSION_FILE_TOO_LARGE,
    HTTP_DETAIL_CAPTURE_SESSION_GROUP_ALREADY_ASSIGNED,
    HTTP_DETAIL_CAPTURE_SESSION_GROUP_ASSIGNMENT_NOT_ALLOWED,
    HTTP_DETAIL_CAPTURE_SESSION_GROUP_INTEGRITY_VIOLATION,
    HTTP_DETAIL_CAPTURE_SESSION_GROUP_NOT_ASSIGNED_FOR_MATERIALIZATION,
    HTTP_DETAIL_CAPTURE_SESSION_GROUP_NOT_ASSIGNED_FOR_PREVIEW,
    HTTP_DETAIL_CAPTURE_SESSION_GROUP_NOT_FOUND,
    HTTP_DETAIL_CAPTURE_SESSION_GROUP_NOT_MATERIALIZED_FOR_PREVIEW,
    HTTP_DETAIL_CAPTURE_SESSION_GROUPING_NOT_ALLOWED,
    HTTP_DETAIL_CAPTURE_SESSION_INVALID_IDEMPOTENCY_KEY,
    HTTP_DETAIL_CAPTURE_SESSION_INVALID_STATE,
    HTTP_DETAIL_CAPTURE_SESSION_MATERIALIZATION_FAILED,
    HTTP_DETAIL_CAPTURE_SESSION_MATERIALIZATION_NOT_ALLOWED,
    HTTP_DETAIL_CAPTURE_SESSION_NO_ITEMS_FOR_GROUPING,
    HTTP_DETAIL_CAPTURE_SESSION_NOT_ACCEPTING_UPLOADS,
    HTTP_DETAIL_CAPTURE_SESSION_NOT_FOUND,
    HTTP_DETAIL_CAPTURE_SESSION_STATUS_FILTER_INVALID,
    HTTP_DETAIL_CLIENT_NOT_FOUND,
    HTTP_DETAIL_CLIENT_SUPPLIER_CLIENT_MISMATCH,
    HTTP_DETAIL_CLIENT_SUPPLIER_NOT_FOUND,
    HTTP_DETAIL_CLIENT_SUPPLIER_REQUIRED_FOR_AISLE,
    HTTP_DETAIL_CODE_SCAN_DISABLED,
    HTTP_DETAIL_CODE_SCAN_EXPORT_NO_RUN,
    HTTP_DETAIL_CODE_SCAN_EXPORT_UNSUPPORTED_FORMAT,
    HTTP_DETAIL_CODE_SCAN_EXPORT_UNSUPPORTED_TYPE,
    HTTP_DETAIL_CODE_SCAN_MAX_ASSETS_EXCEEDED,
    HTTP_DETAIL_CODE_SCAN_SCANNER_UNAVAILABLE,
    HTTP_DETAIL_EMPTY_OR_ZERO_BYTE_FILES_NOT_ALLOWED,
    HTTP_DETAIL_INVENTORY_CLIENT_REQUIRED_FOR_AISLE,
    HTTP_DETAIL_INVENTORY_CLIENT_REQUIRED_FOR_SUPPLIER,
    HTTP_DETAIL_INVENTORY_NOT_FOUND,
    HTTP_DETAIL_JOB_NOT_FOUND,
    HTTP_DETAIL_OPEN_CAPTURE_SESSION_EXISTS,
    HTTP_DETAIL_POSITION_NOT_FOUND_IN_AISLE,
    HTTP_DETAIL_PRODUCT_NOT_FOUND_ON_POSITION,
    HTTP_DETAIL_SUPPLIER_PROMPT_CONFIG_ACTIVATION_FAILED,
    HTTP_DETAIL_SUPPLIER_PROMPT_CONFIG_EMPTY_INSTRUCTIONS,
    HTTP_DETAIL_SUPPLIER_PROMPT_CONFIG_INVALID_MODEL,
    HTTP_DETAIL_SUPPLIER_PROMPT_CONFIG_INVALID_PROVIDER,
    HTTP_DETAIL_SUPPLIER_PROMPT_CONFIG_INVALID_SCOPE,
    HTTP_DETAIL_SUPPLIER_PROMPT_CONFIG_NOT_FOUND,
    HTTP_DETAIL_SUPPLIER_REFERENCE_IMAGE_NOT_FOUND,
    HTTP_DETAIL_TOO_MANY_FILES_PER_UPLOAD,
    HTTP_DETAIL_UNEXPECTED_ERROR,
    HTTP_DETAIL_UPLOAD_FILE_TOO_LARGE,
    HTTP_DETAIL_UPLOAD_REQUEST_TOO_LARGE,
)
from src.api.errors.structured_api_http import (
    ACTIVE_JOB_EXISTS,
    AISLE_HAS_NO_SOURCE_ASSETS_FOR_CODE_SCAN,
    AISLE_HAS_NO_SOURCE_ASSETS_FOR_PROCESSING,
    AISLE_INACTIVE,
    AISLE_NOT_FOUND,
    AISLE_NOT_FOUND_FOR_ASSIGNMENT,
    AISLE_SOURCE_ASSET_MUTATION_BLOCKED,
    ANALYTICS_SCOPE_VALIDATION_FAILED,
    ASSET_NOT_FOUND,
    BENCHMARK_COMPARE_JOBS_MUST_DIFFER,
    BENCHMARK_COMPARE_MANY_INVALID_SELECTION,
    CAPTURE_SESSION_ALREADY_MATERIALIZED,
    CAPTURE_SESSION_DUPLICATE_ITEM_CONTENT,
    CAPTURE_SESSION_GROUP_ALREADY_ASSIGNED,
    CAPTURE_SESSION_GROUP_ASSIGNMENT_NOT_ALLOWED,
    CAPTURE_SESSION_GROUP_INTEGRITY_VIOLATION,
    CAPTURE_SESSION_GROUP_NOT_ASSIGNED_FOR_MATERIALIZATION,
    CAPTURE_SESSION_GROUP_NOT_ASSIGNED_FOR_PREVIEW,
    CAPTURE_SESSION_GROUP_NOT_FOUND,
    CAPTURE_SESSION_GROUP_NOT_MATERIALIZED_FOR_PREVIEW,
    CAPTURE_SESSION_GROUPING_NOT_ALLOWED,
    CAPTURE_SESSION_INVALID_CLOCK_OFFSET,
    CAPTURE_SESSION_INVALID_IDEMPOTENCY_KEY,
    CAPTURE_SESSION_INVALID_STATE,
    CAPTURE_SESSION_MATERIALIZATION_FAILED,
    CAPTURE_SESSION_MATERIALIZATION_NOT_ALLOWED,
    CAPTURE_SESSION_NO_ITEMS_FOR_GROUPING,
    CAPTURE_SESSION_NOT_ACCEPTING_UPLOADS,
    CAPTURE_SESSION_NOT_FOUND,
    CAPTURE_SESSION_PREVIEW_NOT_ALLOWED,
    CAPTURE_SESSION_STAGING_FILE_TOO_LARGE,
    CAPTURE_SESSION_STATUS_FILTER_INVALID,
    CLIENT_NOT_FOUND,
    CLIENT_SUPPLIER_CLIENT_MISMATCH,
    CLIENT_SUPPLIER_NOT_FOUND,
    CLIENT_SUPPLIER_REQUIRED_FOR_AISLE,
    CODE_SCAN_DISABLED,
    CODE_SCAN_EXPORT_NO_RUN,
    CODE_SCAN_EXPORT_UNSUPPORTED_FORMAT,
    CODE_SCAN_EXPORT_UNSUPPORTED_TYPE,
    CODE_SCAN_MAX_ASSETS_EXCEEDED,
    CODE_SCAN_SCANNER_UNAVAILABLE,
    EMPTY_UPLOAD,
    INTERNAL_SERVER_ERROR,
    INVENTORY_CLIENT_REQUIRED_FOR_AISLE,
    INVENTORY_CLIENT_REQUIRED_FOR_SUPPLIER,
    INVENTORY_NOT_FOUND,
    JOB_NOT_FOUND,
    JOB_NOT_IN_AISLE_SCOPE,
    JOB_PROMOTION_NOT_ALLOWED,
    IMAGE_ALREADY_HAS_RESULTS,
    MANUAL_RESULT_ALREADY_EXISTS,
    MANUAL_RESULT_NOT_ALLOWED_FOR_ASSET_TYPE,
    ASSET_NOT_IN_JOB_SNAPSHOT,
    PHOTOS_JOB_REQUIRED,
    OPEN_CAPTURE_SESSION_EXISTS,
    POSITION_NOT_FOUND,
    PRODUCT_NOT_FOUND,
    PROVIDER_INCOMPATIBLE_WITH_JOB,
    SUPPLIER_PROMPT_CONFIG_ACTIVATION_FAILED,
    SUPPLIER_PROMPT_CONFIG_EMPTY_INSTRUCTIONS,
    SUPPLIER_PROMPT_CONFIG_INVALID_MODEL,
    SUPPLIER_PROMPT_CONFIG_INVALID_PROVIDER,
    SUPPLIER_PROMPT_CONFIG_INVALID_SCOPE,
    SUPPLIER_PROMPT_CONFIG_NOT_FOUND,
    SUPPLIER_REFERENCE_IMAGE_NOT_FOUND,
    UNSUPPORTED_ASSET_TYPE,
    UPLOAD_FILE_TOO_LARGE,
    UPLOAD_REQUEST_TOO_LARGE,
    UPLOAD_TOO_MANY_FILES_PER_REQUEST,
    ZERO_BYTE_FILE,
    StructuredApiHttpError,
)
from src.api.services.v3_stored_artifact_access import StoredArtifactAccessError
from src.application.errors import (
    ActiveJobExistsError,
    AisleInactiveError,
    AisleNotFoundError,
    AisleNotFoundForAssignmentError,
    AisleSourceAssetMutationBlockedError,
    AnalyticsScopeValidationError,
    BenchmarkCompareJobsMustDifferError,
    BenchmarkCompareManyInvalidSelectionError,
    BenchmarkRequiresTestInventoryError,
    CaptureSessionAlreadyMaterializedError,
    CaptureSessionDuplicateItemContentError,
    CaptureSessionGroupAlreadyAssignedError,
    CaptureSessionGroupAssignmentNotAllowedError,
    CaptureSessionGroupingNotAllowedError,
    CaptureSessionGroupIntegrityError,
    CaptureSessionGroupNotAssignedForMaterializationError,
    CaptureSessionGroupNotAssignedForPreviewError,
    CaptureSessionGroupNotFoundError,
    CaptureSessionGroupNotMaterializedForPreviewError,
    CaptureSessionInvalidClockOffsetError,
    CaptureSessionInvalidIdempotencyKeyError,
    CaptureSessionInvalidStateError,
    CaptureSessionMaterializationFailedError,
    CaptureSessionMaterializationNotAllowedError,
    CaptureSessionNoItemsForGroupingError,
    CaptureSessionNotAcceptingUploadsError,
    CaptureSessionNotFoundError,
    CaptureSessionPreviewNotAllowedError,
    CaptureSessionStagingFileTooLargeError,
    CaptureSessionStatusFilterInvalidError,
    ClientNotFoundError,
    ClientSupplierClientMismatchError,
    ClientSupplierNotFoundError,
    ClientSupplierRequiredForAisleError,
    CodeScanDisabledError,
    CodeScanExportNoRunError,
    CodeScanExportUnsupportedFormatError,
    CodeScanExportUnsupportedTypeError,
    CodeScanMaxAssetsExceededError,
    CodeScanScannerUnavailableError,
    DeprecatedProcessingProviderError,
    DuplicateAisleCodeError,
    EmptyUploadError,
    InvalidProcessingModelError,
    InvalidProcessingPromptKeyError,
    InventoryClientRequiredForAisleError,
    InventoryClientRequiredForSupplierError,
    InventoryNotFoundError,
    JobDoesNotBelongToAisleError,
    JobNotFoundError,
    JobPromotionNotAllowedError,
    ImageAlreadyHasResultsError,
    ManualResultAlreadyExistsError,
    ManualResultNotAllowedForAssetTypeError,
    MergeJobScopeAmbiguousError,
    NoSourceAssetsForAisleProcessingError,
    NoSourceAssetsForCodeScanError,
    OpenCaptureSessionExistsError,
    PhotosJobRequiredError,
    PositionDeletedError,
    PositionNotFoundError,
    PositionResultContextMismatchError,
    ProcessingProviderIncompatibleWithJobError,
    ProcessingProviderNotConfiguredError,
    ProductNotFoundError,
    ReviewMutationNotAllowedError,
    AssetNotInJobSnapshotError,
    SourceAssetNotFoundForAisleError,
    SupplierPromptConfigActivationFailedError,
    SupplierPromptConfigEmptyInstructionsError,
    SupplierPromptConfigInvalidModelError,
    SupplierPromptConfigInvalidProviderError,
    SupplierPromptConfigInvalidScopeError,
    SupplierPromptConfigNotFoundError,
    SupplierReferenceImageNotFoundError,
    TooManyFilesPerUploadError,
    UnknownProcessingProviderError,
    UnsupportedAssetTypeError,
    ZeroByteFileError,
)
from src.application.services.upload_request_limits import (
    UploadFileTooLargeError,
    UploadRequestTooLargeError,
)

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


def _structured_fixed(
    status_code: int, *, error_code: str, detail: str
) -> Callable[[BaseException], HTTPException]:
    """Build mapper that ignores the exception instance (stable ``detail``)."""

    def _map(_: BaseException) -> HTTPException:
        return StructuredApiHttpError(status_code, error_code=error_code, detail=detail)

    return _map


def _structured_detail(
    status_code: int,
    *,
    error_code: str,
    detail: Callable[[BaseException], str],
) -> Callable[[BaseException], HTTPException]:
    def _map(exc: BaseException) -> HTTPException:
        return StructuredApiHttpError(status_code, error_code=error_code, detail=detail(exc))

    return _map


def _plain_http(status_code: int) -> Callable[[BaseException], HTTPException]:
    """Legacy branch: ``HTTPException`` with ``detail=str(exc)``."""

    def _map(exc: BaseException) -> HTTPException:
        return HTTPException(status_code=status_code, detail=str(exc))

    return _map


def _map_stored_artifact_access(exc: BaseException) -> HTTPException:
    e = cast(StoredArtifactAccessError, exc)
    return HTTPException(status_code=e.status_code, detail=e.detail)


# Ordered dispatch: ``isinstance`` checks run in insertion order (Python 3.7+ ``dict``).
# If two registered types stand in a subclass relationship, the **first** entry wins.
_HTTP_EXCEPTION_DISPATCH: dict[type[BaseException], Callable[[BaseException], HTTPException]] = {
    StoredArtifactAccessError: _map_stored_artifact_access,
    InventoryNotFoundError: _structured_fixed(
        404, error_code=INVENTORY_NOT_FOUND, detail=HTTP_DETAIL_INVENTORY_NOT_FOUND
    ),
    ClientNotFoundError: _structured_fixed(
        404, error_code=CLIENT_NOT_FOUND, detail=HTTP_DETAIL_CLIENT_NOT_FOUND
    ),
    ClientSupplierNotFoundError: _structured_fixed(
        404,
        error_code=CLIENT_SUPPLIER_NOT_FOUND,
        detail=HTTP_DETAIL_CLIENT_SUPPLIER_NOT_FOUND,
    ),
    InventoryClientRequiredForSupplierError: _structured_fixed(
        409,
        error_code=INVENTORY_CLIENT_REQUIRED_FOR_SUPPLIER,
        detail=HTTP_DETAIL_INVENTORY_CLIENT_REQUIRED_FOR_SUPPLIER,
    ),
    ClientSupplierClientMismatchError: _structured_fixed(
        409,
        error_code=CLIENT_SUPPLIER_CLIENT_MISMATCH,
        detail=HTTP_DETAIL_CLIENT_SUPPLIER_CLIENT_MISMATCH,
    ),
    ClientSupplierRequiredForAisleError: _structured_fixed(
        422,
        error_code=CLIENT_SUPPLIER_REQUIRED_FOR_AISLE,
        detail=HTTP_DETAIL_CLIENT_SUPPLIER_REQUIRED_FOR_AISLE,
    ),
    InventoryClientRequiredForAisleError: _structured_fixed(
        422,
        error_code=INVENTORY_CLIENT_REQUIRED_FOR_AISLE,
        detail=HTTP_DETAIL_INVENTORY_CLIENT_REQUIRED_FOR_AISLE,
    ),
    AisleNotFoundError: _structured_fixed(
        404, error_code=AISLE_NOT_FOUND, detail=HTTP_DETAIL_AISLE_NOT_FOUND_IN_INVENTORY
    ),
    PositionNotFoundError: _structured_fixed(
        404, error_code=POSITION_NOT_FOUND, detail=HTTP_DETAIL_POSITION_NOT_FOUND_IN_AISLE
    ),
    ProductNotFoundError: _structured_fixed(
        404, error_code=PRODUCT_NOT_FOUND, detail=HTTP_DETAIL_PRODUCT_NOT_FOUND_ON_POSITION
    ),
    SupplierReferenceImageNotFoundError: _structured_fixed(
        404,
        error_code=SUPPLIER_REFERENCE_IMAGE_NOT_FOUND,
        detail=HTTP_DETAIL_SUPPLIER_REFERENCE_IMAGE_NOT_FOUND,
    ),
    SupplierPromptConfigNotFoundError: _structured_fixed(
        404,
        error_code=SUPPLIER_PROMPT_CONFIG_NOT_FOUND,
        detail=HTTP_DETAIL_SUPPLIER_PROMPT_CONFIG_NOT_FOUND,
    ),
    SourceAssetNotFoundForAisleError: _structured_fixed(
        404, error_code=ASSET_NOT_FOUND, detail=HTTP_DETAIL_ASSET_NOT_FOUND
    ),
    AssetNotInJobSnapshotError: _structured_fixed(
        404,
        error_code=ASSET_NOT_IN_JOB_SNAPSHOT,
        detail="Source asset is not part of this job snapshot",
    ),
    PhotosJobRequiredError: _structured_fixed(
        422,
        error_code=PHOTOS_JOB_REQUIRED,
        detail="Image coverage is only supported for photos jobs",
    ),
    ManualResultNotAllowedForAssetTypeError: _structured_fixed(
        422,
        error_code=MANUAL_RESULT_NOT_ALLOWED_FOR_ASSET_TYPE,
        detail="Manual results are only allowed for primary photo assets",
    ),
    ManualResultAlreadyExistsError: _structured_fixed(
        409,
        error_code=MANUAL_RESULT_ALREADY_EXISTS,
        detail="La imagen ya tiene un resultado manual asociado.",
    ),
    ImageAlreadyHasResultsError: _structured_fixed(
        409,
        error_code=IMAGE_ALREADY_HAS_RESULTS,
        detail="La imagen ya tiene uno o más resultados asociados.",
    ),
    JobNotFoundError: _structured_detail(
        404,
        error_code=JOB_NOT_FOUND,
        detail=lambda e: _normalized_job_not_found_detail(cast(JobNotFoundError, e)),
    ),
    JobDoesNotBelongToAisleError: _structured_detail(
        404,
        error_code=JOB_NOT_IN_AISLE_SCOPE,
        detail=lambda e: _normalized_job_does_not_belong_detail(
            cast(JobDoesNotBelongToAisleError, e)
        ),
    ),
    PositionResultContextMismatchError: _plain_http(409),
    PositionDeletedError: _plain_http(409),
    DuplicateAisleCodeError: _plain_http(409),
    ActiveJobExistsError: _structured_detail(
        409,
        error_code=ACTIVE_JOB_EXISTS,
        detail=lambda e: _normalized_active_job_exists_detail(cast(ActiveJobExistsError, e)),
    ),
    AisleInactiveError: _structured_fixed(
        409,
        error_code=AISLE_INACTIVE,
        detail=HTTP_DETAIL_AISLE_INACTIVE,
    ),
    NoSourceAssetsForAisleProcessingError: _structured_fixed(
        409,
        error_code=AISLE_HAS_NO_SOURCE_ASSETS_FOR_PROCESSING,
        detail=HTTP_DETAIL_AISLE_NO_SOURCE_ASSETS_FOR_PROCESSING,
    ),
    NoSourceAssetsForCodeScanError: _structured_fixed(
        409,
        error_code=AISLE_HAS_NO_SOURCE_ASSETS_FOR_CODE_SCAN,
        detail=HTTP_DETAIL_AISLE_NO_SOURCE_ASSETS_FOR_CODE_SCAN,
    ),
    CodeScanDisabledError: _structured_fixed(
        503,
        error_code=CODE_SCAN_DISABLED,
        detail=HTTP_DETAIL_CODE_SCAN_DISABLED,
    ),
    CodeScanMaxAssetsExceededError: _structured_fixed(
        422,
        error_code=CODE_SCAN_MAX_ASSETS_EXCEEDED,
        detail=HTTP_DETAIL_CODE_SCAN_MAX_ASSETS_EXCEEDED,
    ),
    CodeScanScannerUnavailableError: _structured_fixed(
        503,
        error_code=CODE_SCAN_SCANNER_UNAVAILABLE,
        detail=HTTP_DETAIL_CODE_SCAN_SCANNER_UNAVAILABLE,
    ),
    CodeScanExportNoRunError: _structured_fixed(
        404,
        error_code=CODE_SCAN_EXPORT_NO_RUN,
        detail=HTTP_DETAIL_CODE_SCAN_EXPORT_NO_RUN,
    ),
    CodeScanExportUnsupportedTypeError: _structured_fixed(
        422,
        error_code=CODE_SCAN_EXPORT_UNSUPPORTED_TYPE,
        detail=HTTP_DETAIL_CODE_SCAN_EXPORT_UNSUPPORTED_TYPE,
    ),
    CodeScanExportUnsupportedFormatError: _structured_fixed(
        422,
        error_code=CODE_SCAN_EXPORT_UNSUPPORTED_FORMAT,
        detail=HTTP_DETAIL_CODE_SCAN_EXPORT_UNSUPPORTED_FORMAT,
    ),
    AisleSourceAssetMutationBlockedError: _structured_fixed(
        409,
        error_code=AISLE_SOURCE_ASSET_MUTATION_BLOCKED,
        detail=HTTP_DETAIL_AISLE_SOURCE_ASSETS_ACTIVE_JOB_BLOCKS_MUTATION,
    ),
    BenchmarkRequiresTestInventoryError: _plain_http(409),
    JobPromotionNotAllowedError: _structured_detail(
        409,
        error_code=JOB_PROMOTION_NOT_ALLOWED,
        detail=lambda e: _normalized_job_promotion_not_allowed_detail(
            cast(JobPromotionNotAllowedError, e)
        ),
    ),
    ReviewMutationNotAllowedError: _plain_http(409),
    EmptyUploadError: _structured_fixed(
        422, error_code=EMPTY_UPLOAD, detail=HTTP_DETAIL_AT_LEAST_ONE_FILE_REQUIRED
    ),
    ZeroByteFileError: _structured_fixed(
        422, error_code=ZERO_BYTE_FILE, detail=HTTP_DETAIL_EMPTY_OR_ZERO_BYTE_FILES_NOT_ALLOWED
    ),
    UnknownProcessingProviderError: _plain_http(422),
    DeprecatedProcessingProviderError: _plain_http(422),
    InvalidProcessingModelError: _plain_http(422),
    InvalidProcessingPromptKeyError: _plain_http(422),
    ProcessingProviderIncompatibleWithJobError: _structured_detail(
        422,
        error_code=PROVIDER_INCOMPATIBLE_WITH_JOB,
        detail=lambda e: str(e),
    ),
    ProcessingProviderNotConfiguredError: _plain_http(422),
    BenchmarkCompareJobsMustDifferError: _structured_fixed(
        422,
        error_code=BENCHMARK_COMPARE_JOBS_MUST_DIFFER,
        detail=HTTP_DETAIL_BENCHMARK_COMPARE_JOBS_MUST_DIFFER,
    ),
    BenchmarkCompareManyInvalidSelectionError: _structured_detail(
        422,
        error_code=BENCHMARK_COMPARE_MANY_INVALID_SELECTION,
        detail=lambda e: str(e),
    ),
    MergeJobScopeAmbiguousError: _plain_http(422),
    AnalyticsScopeValidationError: _structured_fixed(
        422,
        error_code=ANALYTICS_SCOPE_VALIDATION_FAILED,
        detail=HTTP_DETAIL_ANALYTICS_SCOPE_VALIDATION_FAILED,
    ),
    CaptureSessionNotFoundError: _structured_fixed(
        404, error_code=CAPTURE_SESSION_NOT_FOUND, detail=HTTP_DETAIL_CAPTURE_SESSION_NOT_FOUND
    ),
    OpenCaptureSessionExistsError: _structured_fixed(
        409,
        error_code=OPEN_CAPTURE_SESSION_EXISTS,
        detail=HTTP_DETAIL_OPEN_CAPTURE_SESSION_EXISTS,
    ),
    CaptureSessionInvalidClockOffsetError: _structured_detail(
        422,
        error_code=CAPTURE_SESSION_INVALID_CLOCK_OFFSET,
        detail=lambda e: str(e),
    ),
    CaptureSessionPreviewNotAllowedError: _structured_detail(
        409,
        error_code=CAPTURE_SESSION_PREVIEW_NOT_ALLOWED,
        detail=lambda e: str(e),
    ),
    CaptureSessionGroupingNotAllowedError: _structured_detail(
        409,
        error_code=CAPTURE_SESSION_GROUPING_NOT_ALLOWED,
        detail=lambda e: str(e) or HTTP_DETAIL_CAPTURE_SESSION_GROUPING_NOT_ALLOWED,
    ),
    CaptureSessionNoItemsForGroupingError: _structured_detail(
        422,
        error_code=CAPTURE_SESSION_NO_ITEMS_FOR_GROUPING,
        detail=lambda e: str(e) or HTTP_DETAIL_CAPTURE_SESSION_NO_ITEMS_FOR_GROUPING,
    ),
    CaptureSessionGroupNotFoundError: _structured_detail(
        404,
        error_code=CAPTURE_SESSION_GROUP_NOT_FOUND,
        detail=lambda e: str(e) or HTTP_DETAIL_CAPTURE_SESSION_GROUP_NOT_FOUND,
    ),
    CaptureSessionGroupNotAssignedForMaterializationError: _structured_detail(
        422,
        error_code=CAPTURE_SESSION_GROUP_NOT_ASSIGNED_FOR_MATERIALIZATION,
        detail=lambda e: (
            str(e) or HTTP_DETAIL_CAPTURE_SESSION_GROUP_NOT_ASSIGNED_FOR_MATERIALIZATION
        ),
    ),
    CaptureSessionGroupNotAssignedForPreviewError: _structured_detail(
        422,
        error_code=CAPTURE_SESSION_GROUP_NOT_ASSIGNED_FOR_PREVIEW,
        detail=lambda e: str(e) or HTTP_DETAIL_CAPTURE_SESSION_GROUP_NOT_ASSIGNED_FOR_PREVIEW,
    ),
    CaptureSessionGroupNotMaterializedForPreviewError: _structured_detail(
        422,
        error_code=CAPTURE_SESSION_GROUP_NOT_MATERIALIZED_FOR_PREVIEW,
        detail=lambda e: str(e) or HTTP_DETAIL_CAPTURE_SESSION_GROUP_NOT_MATERIALIZED_FOR_PREVIEW,
    ),
    CaptureSessionGroupIntegrityError: _structured_detail(
        422,
        error_code=CAPTURE_SESSION_GROUP_INTEGRITY_VIOLATION,
        detail=lambda e: str(e) or HTTP_DETAIL_CAPTURE_SESSION_GROUP_INTEGRITY_VIOLATION,
    ),
    CaptureSessionGroupAlreadyAssignedError: _structured_detail(
        409,
        error_code=CAPTURE_SESSION_GROUP_ALREADY_ASSIGNED,
        detail=lambda e: str(e) or HTTP_DETAIL_CAPTURE_SESSION_GROUP_ALREADY_ASSIGNED,
    ),
    CaptureSessionGroupAssignmentNotAllowedError: _structured_detail(
        409,
        error_code=CAPTURE_SESSION_GROUP_ASSIGNMENT_NOT_ALLOWED,
        detail=lambda e: str(e) or HTTP_DETAIL_CAPTURE_SESSION_GROUP_ASSIGNMENT_NOT_ALLOWED,
    ),
    AisleNotFoundForAssignmentError: _structured_detail(
        404,
        error_code=AISLE_NOT_FOUND_FOR_ASSIGNMENT,
        detail=lambda e: str(e) or HTTP_DETAIL_AISLE_NOT_FOUND_FOR_ASSIGNMENT,
    ),
    CaptureSessionInvalidIdempotencyKeyError: _structured_fixed(
        422,
        error_code=CAPTURE_SESSION_INVALID_IDEMPOTENCY_KEY,
        detail=HTTP_DETAIL_CAPTURE_SESSION_INVALID_IDEMPOTENCY_KEY,
    ),
    CaptureSessionMaterializationNotAllowedError: _structured_fixed(
        409,
        error_code=CAPTURE_SESSION_MATERIALIZATION_NOT_ALLOWED,
        detail=HTTP_DETAIL_CAPTURE_SESSION_MATERIALIZATION_NOT_ALLOWED,
    ),
    CaptureSessionAlreadyMaterializedError: _structured_fixed(
        409,
        error_code=CAPTURE_SESSION_ALREADY_MATERIALIZED,
        detail=HTTP_DETAIL_CAPTURE_SESSION_ALREADY_MATERIALIZED,
    ),
    CaptureSessionMaterializationFailedError: _structured_fixed(
        500,
        error_code=CAPTURE_SESSION_MATERIALIZATION_FAILED,
        detail=HTTP_DETAIL_CAPTURE_SESSION_MATERIALIZATION_FAILED,
    ),
    CaptureSessionInvalidStateError: _structured_fixed(
        409,
        error_code=CAPTURE_SESSION_INVALID_STATE,
        detail=HTTP_DETAIL_CAPTURE_SESSION_INVALID_STATE,
    ),
    CaptureSessionNotAcceptingUploadsError: _structured_fixed(
        409,
        error_code=CAPTURE_SESSION_NOT_ACCEPTING_UPLOADS,
        detail=HTTP_DETAIL_CAPTURE_SESSION_NOT_ACCEPTING_UPLOADS,
    ),
    CaptureSessionDuplicateItemContentError: _structured_fixed(
        409,
        error_code=CAPTURE_SESSION_DUPLICATE_ITEM_CONTENT,
        detail=HTTP_DETAIL_CAPTURE_SESSION_DUPLICATE_CONTENT,
    ),
    TooManyFilesPerUploadError: _structured_fixed(
        400,
        error_code=UPLOAD_TOO_MANY_FILES_PER_REQUEST,
        detail=HTTP_DETAIL_TOO_MANY_FILES_PER_UPLOAD,
    ),
    UploadFileTooLargeError: _structured_fixed(
        422,
        error_code=UPLOAD_FILE_TOO_LARGE,
        detail=HTTP_DETAIL_UPLOAD_FILE_TOO_LARGE,
    ),
    UploadRequestTooLargeError: _structured_fixed(
        422,
        error_code=UPLOAD_REQUEST_TOO_LARGE,
        detail=HTTP_DETAIL_UPLOAD_REQUEST_TOO_LARGE,
    ),
    CaptureSessionStagingFileTooLargeError: _structured_fixed(
        422,
        error_code=CAPTURE_SESSION_STAGING_FILE_TOO_LARGE,
        detail=HTTP_DETAIL_CAPTURE_SESSION_FILE_TOO_LARGE,
    ),
    CaptureSessionStatusFilterInvalidError: _structured_fixed(
        422,
        error_code=CAPTURE_SESSION_STATUS_FILTER_INVALID,
        detail=HTTP_DETAIL_CAPTURE_SESSION_STATUS_FILTER_INVALID,
    ),
    SupplierPromptConfigInvalidProviderError: _structured_fixed(
        400,
        error_code=SUPPLIER_PROMPT_CONFIG_INVALID_PROVIDER,
        detail=HTTP_DETAIL_SUPPLIER_PROMPT_CONFIG_INVALID_PROVIDER,
    ),
    SupplierPromptConfigInvalidModelError: _structured_fixed(
        400,
        error_code=SUPPLIER_PROMPT_CONFIG_INVALID_MODEL,
        detail=HTTP_DETAIL_SUPPLIER_PROMPT_CONFIG_INVALID_MODEL,
    ),
    SupplierPromptConfigEmptyInstructionsError: _structured_fixed(
        400,
        error_code=SUPPLIER_PROMPT_CONFIG_EMPTY_INSTRUCTIONS,
        detail=HTTP_DETAIL_SUPPLIER_PROMPT_CONFIG_EMPTY_INSTRUCTIONS,
    ),
    SupplierPromptConfigInvalidScopeError: _structured_fixed(
        400,
        error_code=SUPPLIER_PROMPT_CONFIG_INVALID_SCOPE,
        detail=HTTP_DETAIL_SUPPLIER_PROMPT_CONFIG_INVALID_SCOPE,
    ),
    SupplierPromptConfigActivationFailedError: _structured_fixed(
        409,
        error_code=SUPPLIER_PROMPT_CONFIG_ACTIVATION_FAILED,
        detail=HTTP_DETAIL_SUPPLIER_PROMPT_CONFIG_ACTIVATION_FAILED,
    ),
    UnsupportedAssetTypeError: _structured_detail(
        400,
        error_code=UNSUPPORTED_ASSET_TYPE,
        detail=lambda e: str(e),
    ),
}


def mapped_http_exception(exc: BaseException) -> HTTPException | None:
    """Return an ``HTTPException`` for registered errors, or ``None`` if not handled here.

    Returns ``None`` for any exception type not explicitly listed below—including
    :class:`ValueError` and other broad builtins—so callers can apply route-specific rules
    or fall through to the global unexpected-error handler.

    Do **not** extend this function with ``ValueError`` (see module docstring): status and
    detail for value-level validation differ by endpoint and must stay explicit at the route
    or use-case boundary.
    """
    for exc_type, build in _HTTP_EXCEPTION_DISPATCH.items():
        if isinstance(exc, exc_type):
            return build(exc)
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
    suffix = (f" context={ctx!r}") if ctx else ""
    logger.exception("Unhandled exception while mapping review error to HTTP%s", suffix)
    return StructuredApiHttpError(
        500,
        error_code=INTERNAL_SERVER_ERROR,
        detail=HTTP_DETAIL_UNEXPECTED_ERROR,
    )
