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
