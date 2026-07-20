"""Phase 6.2 — optional label geometry normalization (safe fallback to original)."""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class NormalizedLabelImage:
    content: bytes
    mime_type: str = "image/jpeg"
    rotated: bool = False
    perspective_corrected: bool = False


class LabelGeometryNormalizer:
    """Minimal geometry prep: EXIF orientation only; never fails the pipeline."""

    def normalize(self, content: bytes, *, enable_perspective: bool = False) -> NormalizedLabelImage:
        if not content:
            return NormalizedLabelImage(content=b"", mime_type="image/jpeg")
        try:
            from PIL import Image, ImageOps
        except ImportError:
            return NormalizedLabelImage(content=content)

        try:
            with Image.open(io.BytesIO(content)) as img:
                img.load()
                transposed = ImageOps.exif_transpose(img)
                rotated = transposed is not img
                if transposed.mode not in ("RGB", "L"):
                    transposed = transposed.convert("RGB")
                elif transposed.mode == "L":
                    transposed = transposed.convert("RGB")
                # Perspective/homography intentionally not implemented yet — fall through.
                if enable_perspective:
                    logger.debug("label_geometry.perspective_skipped reason=not_implemented")
                out = io.BytesIO()
                transposed.save(out, format="JPEG", quality=90)
                return NormalizedLabelImage(
                    content=out.getvalue(),
                    mime_type="image/jpeg",
                    rotated=bool(rotated),
                    perspective_corrected=False,
                )
        except Exception:
            logger.warning("label_geometry.normalize_failed falling_back", exc_info=True)
            return NormalizedLabelImage(content=content)


def validate_normalized_polygon(
    points: list[list[float]] | list[tuple[float, float]],
) -> tuple[tuple[float, float], ...]:
    """Validate normalized polygon: >=3 points, each coord in [0,1], non-degenerate."""
    if not isinstance(points, (list, tuple)) or len(points) < 3:
        raise ValueError("polygon_requires_at_least_3_points")
    out: list[tuple[float, float]] = []
    for p in points:
        if not isinstance(p, (list, tuple)) or len(p) != 2:
            raise ValueError("polygon_point_invalid")
        x, y = float(p[0]), float(p[1])
        if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
            raise ValueError("polygon_coord_out_of_range")
        out.append((x, y))
    xs = {p[0] for p in out}
    ys = {p[1] for p in out}
    if len(xs) == 1 or len(ys) == 1:
        raise ValueError("polygon_degenerate")
    return tuple(out)


__all__ = [
    "LabelGeometryNormalizer",
    "NormalizedLabelImage",
    "validate_normalized_polygon",
]
