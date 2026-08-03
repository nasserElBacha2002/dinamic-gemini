"""Print presets for positioning labels (physical mm + dpi)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PositioningLabelPreset:
    code: str
    width_mm: float
    height_mm: float
    dpi: int
    marker_size_mm: float
    quiet_zone_mm: float
    template_version: int = 2


_PRESETS: dict[str, PositioningLabelPreset] = {
    "MM_100X100": PositioningLabelPreset(
        code="MM_100x100",
        width_mm=100.0,
        height_mm=100.0,
        dpi=300,
        marker_size_mm=45.0,
        quiet_zone_mm=4.0,
        template_version=2,
    ),
    "MM_100X150": PositioningLabelPreset(
        code="MM_100x150",
        width_mm=100.0,
        height_mm=150.0,
        dpi=300,
        marker_size_mm=50.0,
        quiet_zone_mm=4.0,
        template_version=2,
    ),
    "A6": PositioningLabelPreset(
        code="A6",
        width_mm=105.0,
        height_mm=148.0,
        dpi=300,
        marker_size_mm=55.0,
        quiet_zone_mm=4.0,
        template_version=2,
    ),
    "A4_GRID": PositioningLabelPreset(
        code="A4_GRID",
        width_mm=210.0,
        height_mm=297.0,
        dpi=300,
        marker_size_mm=70.0,
        quiet_zone_mm=5.0,
        template_version=2,
    ),
    "THERMAL": PositioningLabelPreset(
        code="THERMAL",
        width_mm=100.0,
        height_mm=100.0,
        dpi=203,
        marker_size_mm=40.0,
        quiet_zone_mm=3.0,
        template_version=2,
    ),
}


def list_positioning_label_presets() -> list[PositioningLabelPreset]:
    return list(_PRESETS.values())


def get_positioning_label_preset(code: str) -> PositioningLabelPreset:
    key = (code or "").strip().upper().replace("-", "_")
    if key not in _PRESETS:
        raise ValueError(f"Unknown positioning label preset: {code}")
    return _PRESETS[key]


def mm_to_px(mm: float, dpi: int) -> int:
    return max(1, int(round(mm * float(dpi) / 25.4)))
