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


class PositionNotFoundError(Exception):
    """Raised when the position does not exist or does not belong to the given aisle."""


class PositionDeletedError(Exception):
    """Raised when a review action is attempted on a position that is already logically deleted."""


class ProductNotFoundError(Exception):
    """Raised when the product does not exist or does not belong to the given position."""
