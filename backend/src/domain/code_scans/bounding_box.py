"""Stable bounding-box JSON contract for code scan detections (Phase 1).

Stored shape (rect in pixel coordinates):

```json
{
  "format": "rect",
  "unit": "pixel",
  "x": 120.0,
  "y": 340.0,
  "width": 180.0,
  "height": 80.0
}
```

Phase 2 scanners must emit this object (or ``null`` when unknown).
"""

from __future__ import annotations

from typing import Any, Literal

BoundingBoxFormat = Literal["rect"]
BoundingBoxUnit = Literal["pixel", "normalized"]

_REQUIRED_RECT_KEYS = ("format", "unit", "x", "y", "width", "height")


def bounding_box_rect(
    *,
    x: float,
    y: float,
    width: float,
    height: float,
    unit: BoundingBoxUnit = "pixel",
) -> dict[str, Any]:
    """Build a persisted/API bounding box object."""
    return {
        "format": "rect",
        "unit": unit,
        "x": float(x),
        "y": float(y),
        "width": float(width),
        "height": float(height),
    }


def parse_bounding_box(raw: Any) -> dict[str, Any] | None:
    """Validate and return bounding box dict, or ``None`` if missing/invalid."""
    if raw is None:
        return None
    if isinstance(raw, str):
        import json

        text = raw.strip()
        if not text:
            return None
        try:
            raw = json.loads(text)
        except json.JSONDecodeError:
            return None
    if not isinstance(raw, dict):
        return None
    fmt = raw.get("format")
    unit = raw.get("unit")
    if fmt != "rect" or unit not in ("pixel", "normalized"):
        return None
    try:
        x = float(raw["x"])
        y = float(raw["y"])
        width = float(raw["width"])
        height = float(raw["height"])
    except (KeyError, TypeError, ValueError):
        return None
    return bounding_box_rect(x=x, y=y, width=width, height=height, unit=unit)
