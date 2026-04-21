"""Fixed English strings for v3 HTTP error bodies (``detail`` and aligned safe 500 text).

**Ownership:** API-layer wire copy only. Do not add log lines, domain exception templates,
or frontend/i18n strings here. Do not import routes or use cases.

**When adding a constant:** confirm the exact string is (or will be) asserted in contract tests
or is clearly user-facing JSON from ``HTTPException`` / ``JSONResponse``; preserve spelling.

Values are API contract surface; change only with coordinated tests and client review.
This module must not import routes, use cases, or domain logic.
"""

# Safe 500 — global unhandled handler + review unknown fallback (must match ``server.py`` contract).
HTTP_DETAIL_UNEXPECTED_ERROR = "An unexpected error occurred."

# Structured Category A — 404 ``detail`` (mapper contract; some routes reuse the same text).
HTTP_DETAIL_INVENTORY_NOT_FOUND = "Inventory not found"
HTTP_DETAIL_AISLE_NOT_FOUND_IN_INVENTORY = "Aisle not found or does not belong to this inventory"
HTTP_DETAIL_POSITION_NOT_FOUND_IN_AISLE = "Position not found or does not belong to this aisle"
HTTP_DETAIL_PRODUCT_NOT_FOUND_ON_POSITION = "Product not found or does not belong to this position"
HTTP_DETAIL_VISUAL_REFERENCE_NOT_FOUND = "Visual reference not found"

# Structured Category B — fixed 422 ``detail`` (must match mapper / use-case emitters).
HTTP_DETAIL_BENCHMARK_COMPARE_JOBS_MUST_DIFFER = (
    "job_a_id and job_b_id must be different benchmark runs"
)
HTTP_DETAIL_ANALYTICS_SCOPE_VALIDATION_FAILED = "aisle_id does not belong to the given inventory_id"

# Mapper normalizer + Category C job-read — generic job-not-found phrase (identical semantics).
HTTP_DETAIL_JOB_NOT_FOUND = "Job not found"

# Route-level validation / assets (duplicated literals, identical semantics).
HTTP_DETAIL_ONLY_FORMAT_CSV_SUPPORTED = "Only format=csv is supported"
HTTP_DETAIL_AT_LEAST_ONE_FILE_REQUIRED = "At least one file is required"
HTTP_DETAIL_ASSET_NOT_FOUND = "Asset not found"
HTTP_DETAIL_AISLE_SOURCE_ASSETS_ACTIVE_JOB_BLOCKS_MUTATION = (
    "Cannot modify aisle source assets while a job is queued, starting, running, or cancel requested for this aisle"
)
# Structured Category B — 409 ``detail`` (aisle/process cannot proceed with current persisted state).
HTTP_DETAIL_AISLE_NO_SOURCE_ASSETS_FOR_PROCESSING = (
    "This aisle has no source assets; upload media before starting processing."
)
HTTP_DETAIL_AISLE_NOT_FOUND_SHORT = "Aisle not found"
HTTP_DETAIL_PREVIEW_NOT_AVAILABLE_FOR_IMAGE = "Preview is not available for this image"

# Category C / job scope (aisles) — distinct phrases; do not merge with other constants.
HTTP_DETAIL_JOB_NOT_IN_AISLE_CATEGORY_C = "Job not found or does not belong to this aisle"
HTTP_DETAIL_JOB_NOT_IN_AISLE_INVENTORY = "Job not found or does not belong to this aisle/inventory"

# Inventory upload validation (v3 inventories routes).
HTTP_DETAIL_EMPTY_OR_ZERO_BYTE_FILES_NOT_ALLOWED = "Empty or zero-byte files are not allowed"

# Analytics query validation (v3 analytics routes).
HTTP_DETAIL_ANALYTICS_DATE_FROM_MUST_BE_ON_OR_BEFORE_DATE_TO = "date_from must be on or before date_to"

# Admin AI inspection (v3 admin routes).
HTTP_DETAIL_ADMIN_AI_UNKNOWN_PROMPT_PROFILE_COMBINATION = (
    "Unknown prompt profile, provider, or parity combination for inspection."
)

# Review queue mutation validation (v3 shared review helpers).
HTTP_DETAIL_REVIEW_CORRECTED_QUANTITY_REQUIRED_FOR_UPDATE_QUANTITY = (
    "corrected_quantity is required for update_quantity"
)
HTTP_DETAIL_REVIEW_SKU_REQUIRED_FOR_UPDATE_SKU = "sku is required for update_sku"
HTTP_DETAIL_REVIEW_POSITION_CODE_REQUIRED_FOR_UPDATE_POSITION_CODE = (
    "position_code is required for update_position_code"
)

# Aisle benchmark / execution export (mutually exclusive query params).
HTTP_DETAIL_EXPORT_PROVIDE_EXACTLY_ONE_OF_RUN_OR_COMPARE_JOBS = (
    "Provide exactly one of: run_job_id (single-run export) or both job_a_id and job_b_id (compare export)."
)

# Review POST dispatch — fixed prefix before dynamic ``action_type`` repr (``reviews.py``).
HTTP_DETAIL_REVIEW_UNKNOWN_ACTION_TYPE_PREFIX = "Unknown action_type: "

# API key middleware (``server.api_key_middleware``) — plain 403 JSON ``detail``.
HTTP_DETAIL_API_KEY_INVALID_OR_MISSING = "Invalid or missing API key"

# Field capture sessions (v3 inventories) — Sprint 2 structured subset.
HTTP_DETAIL_CAPTURE_SESSION_NOT_FOUND = "Capture session not found"
HTTP_DETAIL_OPEN_CAPTURE_SESSION_EXISTS = (
    "An open capture session already exists for this aisle; close or cancel it first."
)
HTTP_DETAIL_CAPTURE_SESSION_INVALID_STATE = "Capture session is not in a valid state for this operation"
HTTP_DETAIL_CAPTURE_SESSION_NOT_ACCEPTING_UPLOADS = (
    "This capture session does not accept new staging uploads"
)
HTTP_DETAIL_CAPTURE_SESSION_DUPLICATE_CONTENT = "Duplicate file content in this capture session"
HTTP_DETAIL_CAPTURE_SESSION_UPLOAD_BATCH_TOO_LARGE = "Too many files in this staging upload request"
HTTP_DETAIL_CAPTURE_SESSION_FILE_TOO_LARGE = "File exceeds maximum upload size for staging uploads"
HTTP_DETAIL_CAPTURE_SESSION_STATUS_FILTER_INVALID = (
    "One or more values in the status query parameter are not valid capture session statuses."
)
