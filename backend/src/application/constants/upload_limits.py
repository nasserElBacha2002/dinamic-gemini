"""Shared upload batch limits (v3 inventory platform).

Runtime values come from AppSettings (env). These defaults match
``MAX_FILES_PER_UPLOAD_REQUEST`` / related settings when env is unset.

Limits apply **per HTTP request**, not to the total number of files the user
may select across auto-batched multipart uploads.
"""

from __future__ import annotations

# Defaults aligned with env defaults in grouped_settings / frontend bulkUpload.config.
MAX_FILES_PER_UPLOAD_REQUEST = 10
MAX_UPLOAD_FILE_SIZE_MB = 25
MAX_UPLOAD_REQUEST_SIZE_MB = 100

# Backward-compatible alias used by older imports/tests.
MAX_FILES_PER_UPLOAD = MAX_FILES_PER_UPLOAD_REQUEST
