"""
Shared application-layer exceptions — v3.0.

Raised by use cases; mapped to HTTP by the API layer.
Import from here instead of defining in a single use case module.
"""

from __future__ import annotations


class AisleNotFoundError(Exception):
    """Raised when the aisle does not exist or does not belong to the given inventory."""


class ActiveJobExistsError(Exception):
    """Raised when the aisle already has a job in QUEUED or RUNNING state."""


class InventoryNotFoundError(Exception):
    """Raised when the parent inventory does not exist."""


class DuplicateAisleCodeError(Exception):
    """Raised when an aisle with the same code already exists in the inventory."""


class UnsupportedAssetTypeError(Exception):
    """Raised when an uploaded file has a content type that is not image/* or video/*."""


class EmptyUploadError(Exception):
    """Raised when no files are provided for an aisle asset upload."""


class NoSourceAssetsForAisleProcessingError(Exception):
    """Raised when aisle processing is requested but the aisle has no persisted SourceAsset rows."""


class SourceAssetNotFoundForAisleError(Exception):
    """Raised when a source asset id is unknown or does not belong to the scoped aisle."""


class AisleSourceAssetMutationBlockedError(Exception):
    """Raised when aisle source assets cannot be changed while an active processing job exists."""


class ZeroByteFileError(Exception):
    """Raised when an uploaded file has size zero or negative (empty file not allowed)."""


class MaxInventoryVisualReferencesExceededError(Exception):
    """Raised when uploading would exceed the maximum visual references per inventory."""


class InventoryVisualReferenceNotFoundError(Exception):
    """Raised when the requested inventory visual reference does not exist or is not owned by the inventory."""


class PositionNotFoundError(Exception):
    """Raised when the position does not exist or does not belong to the given aisle."""


class PositionDeletedError(Exception):
    """Raised when a review action is attempted on a position that is already logically deleted."""


class ReviewMutationNotAllowedError(Exception):
    """Raised when a review mutation targets a position outside the operational result slice."""


class ProductNotFoundError(Exception):
    """Raised when the product does not exist or does not belong to the given position."""


class MergeJobScopeAmbiguousError(Exception):
    """Raised when manual merge cannot infer a single job scope (multi-run aisle without job_id)."""


class JobNotFoundError(Exception):
    """Raised when an inventory job id does not exist."""


class JobDoesNotBelongToAisleError(Exception):
    """Raised when a job exists but is not scoped to the given aisle."""


class PositionResultContextMismatchError(Exception):
    """Raised when a position row does not belong to the resolved result context.

    Typical cause: default read slice (operational or legacy) does not match ``position.job_id``;
    client must pass an explicit ``job_id`` matching that row or fix the operational pointer.
    """


class UnknownProcessingProviderError(Exception):
    """Raised when the client requests a pipeline provider key that is not registered."""


class ProcessingProviderNotConfiguredError(Exception):
    """Raised when the client explicitly selects a provider that is missing required credentials."""


class InvalidProcessingModelError(Exception):
    """Raised when model_name is not in the catalog for the selected provider."""


class InvalidProcessingPromptKeyError(Exception):
    """Raised when prompt_key is not a registered hybrid prompt profile."""


class JobPromotionNotAllowedError(Exception):
    """Raised when a benchmark run cannot be promoted to operational (wrong scope, state, or type)."""


class BenchmarkCompareJobsMustDifferError(Exception):
    """Raised when compare is requested with identical job ids (invalid benchmark pair)."""


class BenchmarkRequiresTestInventoryError(Exception):
    """Raised when a benchmark / compare / promote feature is used on a production inventory."""

    def __init__(self, message: str = "This feature is only available for test inventories.") -> None:
        super().__init__(message)


class BenchmarkCompareManyInvalidSelectionError(Exception):
    """Raised when compare-many job selection is invalid (size, uniqueness, baseline membership)."""


class AnalyticsScopeValidationError(Exception):
    """Raised when analytics filters combine ``inventory_id`` and ``aisle_id`` inconsistently."""


class CaptureSessionNotFoundError(Exception):
    """Raised when a capture session is missing or not scoped to the requested inventory/aisle."""


class OpenCaptureSessionExistsError(Exception):
    """Raised when creating a session would exceed the allowed number of open sessions for the aisle."""


class CaptureSessionInvalidStateError(Exception):
    """Raised when a session lifecycle transition is not allowed for the current status."""


class CaptureSessionNotAcceptingUploadsError(Exception):
    """Raised when staging uploads are blocked (terminal state, cancelled, or closed session)."""


class CaptureSessionDuplicateItemContentError(Exception):
    """Raised when the same content hash is already registered for this session (unique index)."""


class CaptureSessionUploadBatchTooLargeError(Exception):
    """Raised when the number of files in one staging upload exceeds the configured cap."""


class CaptureSessionStagingFileTooLargeError(Exception):
    """Raised when a single staging upload exceeds the configured max upload size."""


class CaptureSessionStatusFilterInvalidError(Exception):
    """Raised when GET .../capture-sessions ``status`` query contains unknown or empty tokens."""


class CaptureSessionConfirmLedgerDuplicateError(Exception):
    """Raised when inserting a duplicate (session_id, idempotency_key) into the confirm ledger."""


class CaptureSessionInvalidClockOffsetError(Exception):
    """Raised when ``clock_offset_seconds`` is outside the configured safe range."""


class CaptureSessionPreviewNotAllowedError(Exception):
    """Raised when assignment preview cannot run for the current session state or scope."""
