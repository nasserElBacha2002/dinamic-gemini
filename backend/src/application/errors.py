"""
Shared application-layer exceptions — v3.0.

Raised by use cases; mapped to HTTP by the API layer.
Import from here instead of defining in a single use case module.
"""

from __future__ import annotations


class AisleNotFoundError(Exception):
    """Raised when the aisle does not exist or does not belong to the given inventory."""


class AisleInactiveError(Exception):
    """Raised when an operation requires an active aisle but the aisle is soft-deactivated."""


class ActiveJobExistsError(Exception):
    """Raised when the aisle already has a job in QUEUED or RUNNING state."""


class InventoryNotFoundError(Exception):
    """Raised when the parent inventory does not exist."""


class ClientNotFoundError(Exception):
    """Raised when a client does not exist."""


class InvalidClientNameError(Exception):
    """Raised when client name is missing or invalid."""


class ClientSupplierNotFoundError(Exception):
    """Raised when a client supplier does not exist in the scoped client."""


class InventoryClientRequiredForSupplierError(Exception):
    """Raised when assigning a supplier to an inventory that has no client association."""


class ClientSupplierRequiredForAisleError(Exception):
    """Raised when creating an aisle under a client-oriented inventory without a supplier."""


class InventoryClientRequiredForAisleError(Exception):
    """Raised when creating an aisle under a legacy inventory that has no client association."""


class ClientSupplierClientMismatchError(Exception):
    """Raised when supplier.client_id does not match inventory.client_id."""


class InvalidClientSupplierNameError(Exception):
    """Raised when supplier name is missing or invalid."""


class DuplicateClientSupplierNameError(Exception):
    """Raised when a supplier with the same name already exists under a client."""


class DuplicateAisleCodeError(Exception):
    """Raised when an aisle with the same code already exists in the inventory."""


class UnsupportedAssetTypeError(Exception):
    """Raised when an uploaded file has a content type that is not image/* or video/*."""


class DuplicateUploadIdempotencyKeyError(Exception):
    """Raised on a concurrent-insert race for the same (aisle_id, upload_batch_id, client_file_id).

    The unique index ``UQ_source_assets_aisle_upload_batch_client`` is the source of truth;
    callers should treat this as "another request already persisted this file" and fetch the
    existing row via ``get_by_upload_idempotency_key`` instead of failing the upload.
    """


class EmptyUploadError(Exception):
    """Raised when no files are provided for an aisle asset upload."""


class NoSourceAssetsForCodeScanError(Exception):
    """Raised when a code scan is requested but the aisle has no persisted SourceAsset rows."""


class CodeScanDisabledError(Exception):
    """Raised when aisle code scan is disabled via configuration."""


class CodeScanMaxAssetsExceededError(Exception):
    """Raised when an aisle exceeds the configured max assets per code scan run."""


class CodeScanScannerUnavailableError(Exception):
    """Raised when pyzbar/libzbar is not installed or cannot load in this runtime."""


class CodeScanExportNoRunError(Exception):
    """Raised when a code scan export is requested but no latest run exists for the aisle."""


class CodeScanExportUnsupportedTypeError(Exception):
    """Raised when export type is not detections, unmatched, or summary."""


class CodeScanExportUnsupportedFormatError(Exception):
    """Raised when export format is not csv."""


class NoSourceAssetsForAisleProcessingError(Exception):
    """Raised when aisle processing is requested but the aisle has no persisted SourceAsset rows."""


class SourceAssetNotFoundForAisleError(Exception):
    """Raised when a source asset id is unknown or does not belong to the scoped aisle."""


class AisleSourceAssetMutationBlockedError(Exception):
    """Raised when aisle source assets cannot be changed while an active processing job exists."""


class ZeroByteFileError(Exception):
    """Raised when an uploaded file has size zero or negative (empty file not allowed)."""


class SupplierReferenceImageNotFoundError(Exception):
    """Raised when the requested supplier reference image does not exist or is not owned by the supplier."""


class SupplierPromptConfigNotFoundError(Exception):
    """Raised when a supplier prompt config does not exist or is out of the requested supplier scope."""


class SupplierPromptConfigInvalidProviderError(Exception):
    """Raised when provider_name is empty or not supported."""


class SupplierPromptConfigInvalidModelError(Exception):
    """Raised when model_name is not valid for the selected provider."""


class SupplierPromptConfigEmptyInstructionsError(Exception):
    """Raised when instructions_text is empty or blank."""


class SupplierPromptConfigInvalidScopeError(Exception):
    """Raised when prompt-config scope filters are inconsistent (e.g. model without provider)."""


class SupplierPromptConfigActivationFailedError(Exception):
    """Raised when prompt-config activation does not return an activated row."""


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


class DeprecatedProcessingProviderError(Exception):
    """Raised when the client requests a registered but inactive (deprecated) pipeline provider."""


class ProcessingProviderNotConfiguredError(Exception):
    """Raised when the client explicitly selects a provider that is missing required credentials."""


class InvalidProcessingModelError(Exception):
    """Raised when model_name is not in the catalog for the selected provider."""


class InvalidProcessingPromptKeyError(Exception):
    """Raised when prompt_key is not a registered hybrid prompt profile."""


class ProcessingProviderIncompatibleWithJobError(Exception):
    """Raised when provider/model capabilities do not satisfy the job type (Phase 5)."""

    def __init__(
        self,
        message: str,
        *,
        provider_key: str | None = None,
        model_name: str | None = None,
        resolved_provider_key: str | None = None,
        job_kind: str | None = None,
    ) -> None:
        super().__init__(message)
        self.provider_key = provider_key
        self.model_name = model_name
        self.resolved_provider_key = resolved_provider_key
        self.job_kind = job_kind


class JobPromotionNotAllowedError(Exception):
    """Raised when a benchmark run cannot be promoted to operational (wrong scope, state, or type)."""


class BenchmarkCompareJobsMustDifferError(Exception):
    """Raised when compare is requested with identical job ids (invalid benchmark pair)."""


class BenchmarkRequiresTestInventoryError(Exception):
    """Raised when a benchmark / compare / promote feature is used on a production inventory."""

    def __init__(
        self, message: str = "This feature is only available for test inventories."
    ) -> None:
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


class TooManyFilesPerUploadError(Exception):
    """Raised when a multipart upload request includes more files than allowed per batch."""


class CaptureSessionUploadBatchTooLargeError(TooManyFilesPerUploadError):
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


class CaptureSessionMaterializationNotAllowedError(Exception):
    """Raised when materialization cannot run for the current session state or item set."""


class CaptureSessionMaterializationFailedError(Exception):
    """Raised when materialization fails after entering the operation (storage/persistence/runtime)."""


class CaptureSessionAlreadyMaterializedError(Exception):
    """Raised when a session has already been materialized and a different idempotency key is used."""


class CaptureSessionInvalidIdempotencyKeyError(Exception):
    """Raised when materialization/confirm idempotency key is missing or invalid."""


class CaptureSessionGroupingNotAllowedError(Exception):
    """Raised when temporal grouping cannot run for the current session (not closed, terminal, etc.)."""


class CaptureSessionNoItemsForGroupingError(Exception):
    """Raised when no imported items with capture timestamps exist to form groups."""


class CaptureSessionGroupNotFoundError(Exception):
    """Raised when a temporal group id is unknown for the given capture session."""


class CaptureSessionGroupAlreadyAssignedError(Exception):
    """Raised when a group already has an aisle assignment (G4)."""


class CaptureSessionGroupAssignmentNotAllowedError(Exception):
    """Raised when aisle assignment to a group is not allowed for the current session state (G4)."""


class AisleNotFoundForAssignmentError(Exception):
    """Raised when the target aisle does not exist or does not belong to the session's inventory (G4)."""


class CaptureSessionGroupNotAssignedForMaterializationError(Exception):
    """Raised when materialize-group is called on a group that is still unassigned (G5)."""


class CaptureSessionGroupNotAssignedForPreviewError(Exception):
    """Raised when G6 group preview is requested before the temporal group is assigned to an aisle."""


class CaptureSessionGroupNotMaterializedForPreviewError(Exception):
    """Raised when G6 preview requires at least one materialized SourceAsset for the group (G6)."""


class CaptureSessionGroupIntegrityError(Exception):
    """G7 — defensive invariant violation (session/group/item linkage or preview/materialize scope)."""


class InputSnapshotPersistError(Exception):
    """Raised when persisting the job input snapshot fails and Observability requires it.

    ``code`` is a stable machine-readable identifier for API/log correlation
    (see ``OBSERVABILITY_INPUT_SNAPSHOT_REQUIRED``).
    """

    code = "INPUT_SNAPSHOT_PERSIST_FAILED"

    def __init__(self, message: str, *, cause: Exception | None = None) -> None:
        super().__init__(message)
        self.cause = cause
