"""Shared optional-field sentinel for PATCH bodies (null clears; omit leaves unchanged)."""

from __future__ import annotations

from typing import TypeAlias

from src.domain.aisle_identification.modes import AisleIdentificationMode


class UnsetType:
    """Sentinel: field omitted from a partial update."""

    __slots__ = ()

    def __repr__(self) -> str:
        return "UNSET"


UNSET = UnsetType()

# ``str`` allowed so API routes can pass Literal wire values before domain parse.
OptionalModeUpdate: TypeAlias = AisleIdentificationMode | str | None | UnsetType
