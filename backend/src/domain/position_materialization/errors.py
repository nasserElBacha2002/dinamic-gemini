"""Expected materialization failures mapped by the application service."""

from __future__ import annotations


class PositionMaterializationError(Exception):
    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code


class PositionMaterializationScopeError(PositionMaterializationError):
    pass


class PositionMaterializationConflictError(PositionMaterializationError):
    pass


class PositionMaterializationInventoryStateError(PositionMaterializationError):
    pass


class PositionMaterializationRetryableError(PositionMaterializationError):
    pass


class PositionMaterializationInvariantError(PositionMaterializationError):
    """A non-retryable internal persistence/schema invariant failure."""

    pass
