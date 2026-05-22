"""Stable bounding-box JSON contract for code scan detections.

Supported shapes:

``rect`` (Phase 1):

```json
{"format": "rect", "unit": "pixel", "x": 120, "y": 340, "width": 180, "height": 80}
```

``rect_polygon`` (Phase 2 pyzbar):

```json
{
  "format": "rect_polygon",
  "unit": "pixel",
  "rect": {"x": 120, "y": 340, "width": 180, "height": 80},
  "polygon": [[120, 340], [300, 340], [300, 420], [120, 420]]
}
```
"""

from __future__ import annotations

from typing import Any, Literal

BoundingBoxFormat = Literal["rect", "rect_polygon"]
BoundingBoxUnit = Literal["pixel", "normalized"]


def bounding_box_rect(
    *,
    x: float,
    y: float,
    width: float,
    height: float,
    unit: BoundingBoxUnit = "pixel",
) -> dict[str, Any]:
    return {
        "format": "rect",
        "unit": unit,
        "x": float(x),
        "y": float(y),
        "width": float(width),
        "height": float(height),
    }


def bounding_box_rect_polygon(
    *,
    left: float,
    top: float,
    width: float,
    height: float,
    polygon: list[list[float]],
    unit: BoundingBoxUnit = "pixel",
) -> dict[str, Any]:
    return {
        "format": "rect_polygon",
        "unit": unit,
        "rect": {
            "x": float(left),
            "y": float(top),
            "width": float(width),
            "height": float(height),
        },
        "polygon": [[float(p[0]), float(p[1])] for p in polygon],
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
    if unit not in ("pixel", "normalized"):
        return None
    if fmt == "rect":
        try:
            return bounding_box_rect(
                x=float(raw["x"]),
                y=float(raw["y"]),
                width=float(raw["width"]),
                height=float(raw["height"]),
                unit=unit,
            )
        except (KeyError, TypeError, ValueError):
            return None
    if fmt == "rect_polygon":
        rect = raw.get("rect")
        polygon = raw.get("polygon")
        if not isinstance(rect, dict) or not isinstance(polygon, list):
            return None
        try:
            points = [[float(p[0]), float(p[1])] for p in polygon]
            return bounding_box_rect_polygon(
                left=float(rect["x"]),
                top=float(rect["y"]),
                width=float(rect["width"]),
                height=float(rect["height"]),
                polygon=points,
                unit=unit,
            )
        except (KeyError, TypeError, ValueError, IndexError):
            return None
    return None
