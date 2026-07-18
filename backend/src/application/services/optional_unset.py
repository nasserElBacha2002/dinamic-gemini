"""Shared optional-field sentinel for PATCH bodies (null clears; omit leaves unchanged)."""

from __future__ import annotations


class _UnsetType:
    __slots__ = ()

    def __repr__(self) -> str:
        return "UNSET"


UNSET = _UnsetType()
Unset = _UnsetType  # type alias for annotations
