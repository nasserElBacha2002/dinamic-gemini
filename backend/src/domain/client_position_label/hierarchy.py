"""Position label hierarchy value object (pallet / side / level / marker)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class PositionSide(str, Enum):
    LEFT = "LEFT"
    RIGHT = "RIGHT"


def localize_side_es(side: PositionSide | str) -> str:
    """Spanish display for warehouse side."""
    value = side.value if isinstance(side, PositionSide) else str(side).strip().upper()
    if value == PositionSide.LEFT.value:
        return "Izquierda"
    if value == PositionSide.RIGHT.value:
        return "Derecha"
    raise ValueError(f"unsupported side: {side!r}")


@dataclass(frozen=True)
class PositionHierarchy:
    pallet: str
    side: PositionSide
    level: int
    marker_index: int
    marker_total: int

    def __post_init__(self) -> None:
        pallet = (self.pallet or "").strip()
        if not pallet:
            raise ValueError("pallet is required")
        object.__setattr__(self, "pallet", pallet)
        if not isinstance(self.side, PositionSide):
            raise ValueError("side must be PositionSide.LEFT or PositionSide.RIGHT")
        if int(self.level) < 1:
            raise ValueError("level must be >= 1")
        object.__setattr__(self, "level", int(self.level))
        index = int(self.marker_index)
        total = int(self.marker_total)
        if index < 1:
            raise ValueError("marker_index must be >= 1")
        if total < 1:
            raise ValueError("marker_total must be >= 1")
        if index > total:
            raise ValueError("marker_index must be <= marker_total")
        object.__setattr__(self, "marker_index", index)
        object.__setattr__(self, "marker_total", total)

    def _marker_width(self) -> int:
        if self.marker_total <= 99:
            return 2
        return len(str(self.marker_total))

    def format_marker(self) -> str:
        """Zero-padded marker index (2 digits when total<=99; else width of total)."""
        return f"{self.marker_index:0{self._marker_width()}d}"

    def format_marker_total(self) -> str:
        return f"{self.marker_total:0{self._marker_width()}d}"

    def formatted_marker_pair(self) -> str:
        return f"{self.format_marker()}/{self.format_marker_total()}"

    def display_name(self) -> str:
        """Human-readable name, e.g. ``P12 LEFT N3 01/03``."""
        return (
            f"{self.pallet} {self.side.value} N{self.level} "
            f"{self.formatted_marker_pair()}"
        )

    def canonical_key(self) -> str:
        """Stable equality key (normalized pallet, side, level, markers)."""
        return (
            f"{self.pallet.upper()}|{self.side.value}|"
            f"{self.level}|{self.marker_index}|{self.marker_total}"
        )
