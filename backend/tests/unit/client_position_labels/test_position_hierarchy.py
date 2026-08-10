"""Unit tests — position label hierarchy VO."""

from __future__ import annotations

import pytest

from src.domain.client_position_label.hierarchy import (
    PositionHierarchy,
    PositionSide,
    localize_side_es,
)


def test_hierarchy_display_and_marker_padding() -> None:
    h = PositionHierarchy(
        pallet="P12",
        side=PositionSide.LEFT,
        level=3,
        marker_index=1,
        marker_total=3,
    )
    assert h.format_marker() == "01"
    assert h.formatted_marker_pair() == "01/03"
    assert h.display_name() == "P12 LEFT N3 01/03"
    assert h.canonical_key() == "P12|LEFT|3|1|3"
    assert localize_side_es(PositionSide.LEFT) == "Izquierda"
    assert localize_side_es(PositionSide.RIGHT) == "Derecha"


def test_hierarchy_rejects_invalid_markers() -> None:
    with pytest.raises(ValueError, match="marker_index"):
        PositionHierarchy(
            pallet="P1",
            side=PositionSide.RIGHT,
            level=1,
            marker_index=0,
            marker_total=3,
        )
    with pytest.raises(ValueError, match="marker_index must be <="):
        PositionHierarchy(
            pallet="P1",
            side=PositionSide.RIGHT,
            level=1,
            marker_index=4,
            marker_total=3,
        )
    with pytest.raises(ValueError, match="level"):
        PositionHierarchy(
            pallet="P1",
            side=PositionSide.LEFT,
            level=0,
            marker_index=1,
            marker_total=1,
        )


def test_hierarchy_marker_width_above_99() -> None:
    h = PositionHierarchy(
        pallet="P9",
        side=PositionSide.LEFT,
        level=1,
        marker_index=7,
        marker_total=100,
    )
    assert h.format_marker() == "007"
    assert h.formatted_marker_pair() == "007/100"
