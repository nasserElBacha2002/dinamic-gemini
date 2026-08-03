"""Structured business errors for manual product-position overrides."""

from __future__ import annotations

from typing import Any


class PositionOverrideError(Exception):
    code = "POSITION_OVERRIDE_NOT_FOUND"
    http_status = 400

    def __init__(self, detail: str, **metadata: Any) -> None:
        super().__init__(detail)
        self.detail = detail
        self.metadata = metadata


class PositionOverrideFeatureDisabledError(PositionOverrideError):
    code = "POSITION_OVERRIDE_FEATURE_DISABLED"
    http_status = 403


class PositionOverrideNotFoundError(PositionOverrideError):
    code = "POSITION_OVERRIDE_NOT_FOUND"
    http_status = 404


class PositionOverrideResultNotFoundError(PositionOverrideError):
    code = "POSITION_OVERRIDE_RESULT_NOT_FOUND"
    http_status = 404


class PositionOverrideResultNotActiveError(PositionOverrideError):
    code = "POSITION_OVERRIDE_RESULT_NOT_ACTIVE"
    http_status = 409


class PositionOverrideInvalidActionError(PositionOverrideError):
    code = "POSITION_OVERRIDE_INVALID_ACTION"
    http_status = 422


class PositionOverrideInvalidLabelError(PositionOverrideError):
    code = "POSITION_OVERRIDE_INVALID_LABEL"
    http_status = 422


class PositionOverrideLabelInvalidatedError(PositionOverrideError):
    code = "POSITION_OVERRIDE_LABEL_INVALIDATED"
    http_status = 422


class PositionOverrideCrossTenantError(PositionOverrideError):
    code = "POSITION_OVERRIDE_CROSS_TENANT"
    http_status = 404


class PositionOverrideAccessDeniedError(PositionOverrideError):
    code = "POSITION_OVERRIDE_ACCESS_DENIED"
    http_status = 403


class PositionOverrideConflictError(PositionOverrideError):
    code = "POSITION_OVERRIDE_CONFLICT"
    http_status = 409


class PositionOverrideVersionMismatchError(PositionOverrideConflictError):
    code = "POSITION_OVERRIDE_VERSION_MISMATCH"


class PositionOverrideIdempotencyConflictError(PositionOverrideError):
    code = "POSITION_OVERRIDE_IDEMPOTENCY_CONFLICT"
    http_status = 409


class PositionOverrideAutomaticNotAvailableError(PositionOverrideError):
    code = "POSITION_OVERRIDE_AUTOMATIC_NOT_AVAILABLE"
    http_status = 409
