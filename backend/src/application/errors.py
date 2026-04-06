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
