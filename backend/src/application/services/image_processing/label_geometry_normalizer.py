"""Label geometry normalization — EXIF orient, crop selected region, optional deskew.

Preserves Phase 6.2 helpers (`validate_normalized_polygon`, full-image EXIF normalize)
and adds region crop used by INTERNAL_OCR label detection.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass

from src.application.ports.internal_label_reader import PreparedImage
from src.application.services.image_processing.label_region_detector import LabelRegionCandidate

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class NormalizedLabelImage:
    content: bytes
    mime_type: str = "image/jpeg"
    rotated: bool = False
    perspective_corrected: bool = False


@dataclass(frozen=True)
class GeometryNormalizeResult:
    image_bytes: bytes
    width: int
    height: int
    applied_rotation_deg: float
    perspective_corrected: bool
    used_original_region: bool
    failure_reason: str | None = None


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


class LabelGeometryNormalizer:
    """Crop selected label with margin; optionally deskew. Recoverable OpenCV failures fall back."""

    def __init__(
        self,
        *,
        margin_ratio: float = 0.04,
        upscale_min_side: int = 640,
        allow_perspective_correction: bool = True,
    ) -> None:
        self._margin_ratio = max(0.0, min(0.25, float(margin_ratio)))
        self._upscale_min_side = max(0, int(upscale_min_side))
        self._allow_perspective = bool(allow_perspective_correction)

    def normalize(
        self, content: bytes, *, enable_perspective: bool = False
    ) -> NormalizedLabelImage:
        """Legacy Phase 6.2 full-image EXIF orientation (never fails the pipeline)."""
        return self._normalize_full_image(content, enable_perspective=enable_perspective)

    def normalize_region(
        self,
        image_bytes: bytes,
        candidate: LabelRegionCandidate | None,
        *,
        allow_full_image_fallback: bool = True,
    ) -> GeometryNormalizeResult:
        """Crop selected label region (or fall back to full image when allowed)."""
        return self._normalize_region(
            image_bytes,
            candidate,
            allow_full_image_fallback=allow_full_image_fallback,
        )

    def _normalize_full_image(
        self, content: bytes, *, enable_perspective: bool = False
    ) -> NormalizedLabelImage:
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
                if enable_perspective:
                    logger.debug("label_geometry.perspective_skipped reason=use_region_path")
                out = io.BytesIO()
                transposed.save(out, format="JPEG", quality=90)
                return NormalizedLabelImage(
                    content=out.getvalue(),
                    mime_type="image/jpeg",
                    rotated=bool(rotated),
                    perspective_corrected=False,
                )
        except (OSError, ValueError, TypeError) as exc:
            logger.warning("label_geometry.normalize_failed falling_back err=%s", exc)
            return NormalizedLabelImage(content=content)

    def _normalize_region(
        self,
        image_bytes: bytes,
        candidate: LabelRegionCandidate | None,
        *,
        allow_full_image_fallback: bool = True,
    ) -> GeometryNormalizeResult:
        from PIL import Image, ImageOps

        with Image.open(io.BytesIO(image_bytes)) as img:
            oriented = ImageOps.exif_transpose(img) or img
            rgb = oriented.convert("RGB")
            width, height = rgb.size

            if candidate is None or candidate.bbox_px is None:
                if not allow_full_image_fallback:
                    raise ValueError("LABEL_REGION_REQUIRED")
                out = self._maybe_upscale(rgb)
                return self._to_result(out, rotation=0.0, perspective=False, used_original=True)

            x, y, w, h = candidate.bbox_px
            mx = int(w * self._margin_ratio)
            my = int(h * self._margin_ratio)
            left = max(0, x - mx)
            top = max(0, y - my)
            right = min(width, x + w + mx)
            bottom = min(height, y + h + my)
            if right <= left or bottom <= top:
                if allow_full_image_fallback:
                    out = self._maybe_upscale(rgb)
                    return self._to_result(
                        out,
                        rotation=0.0,
                        perspective=False,
                        used_original=True,
                        failure="INVALID_CROP_BBOX",
                    )
                raise ValueError("INVALID_CROP_BBOX")

            crop = rgb.crop((left, top, right, bottom))
            perspective = False
            rotation = 0.0
            if self._allow_perspective:
                try:
                    crop, perspective, rotation = self._try_deskew(crop)
                except (ImportError, OSError, ValueError, RuntimeError) as exc:
                    logger.debug("label_geometry.deskew_skipped err=%s", exc)

            out = self._maybe_upscale(crop)
            return self._to_result(
                out,
                rotation=rotation,
                perspective=perspective,
                used_original=False,
            )

    def to_prepared(self, result: GeometryNormalizeResult, *, variant_name: str) -> PreparedImage:
        return PreparedImage(
            content=result.image_bytes,
            width=result.width,
            height=result.height,
            variant_name=variant_name,
            mime_type="image/png",
            metadata={
                "geometry_normalized": True,
                "applied_rotation_deg": result.applied_rotation_deg,
                "perspective_corrected": result.perspective_corrected,
                "used_original_region": result.used_original_region,
            },
        )

    def _maybe_upscale(self, image):
        if self._upscale_min_side <= 0:
            return image
        w, h = image.size
        shortest = min(w, h)
        if shortest >= self._upscale_min_side:
            return image
        scale = self._upscale_min_side / float(shortest)
        return image.resize((max(1, int(w * scale)), max(1, int(h * scale))))

    def _try_deskew(self, crop):
        import cv2
        import numpy as np

        arr = np.asarray(crop.convert("RGB"))
        gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
        edges = cv2.Canny(gray, 50, 150, apertureSize=3)
        lines = cv2.HoughLines(edges, 1, np.pi / 180, threshold=80)
        angle = 0.0
        if lines is not None and len(lines) > 0:
            angles = []
            for rho_theta in lines[:40]:
                _rho, theta = rho_theta[0]
                deg = (theta * 180.0 / np.pi) - 90.0
                if -45.0 <= deg <= 45.0:
                    angles.append(deg)
            if angles:
                angle = float(sorted(angles)[len(angles) // 2])
        if abs(angle) < 0.5 or abs(angle) > 15.0:
            return crop, False, 0.0
        (h, w) = gray.shape[:2]
        matrix = cv2.getRotationMatrix2D((w / 2.0, h / 2.0), angle, 1.0)
        rotated = cv2.warpAffine(
            arr,
            matrix,
            (w, h),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REPLICATE,
        )
        from PIL import Image

        return Image.fromarray(rotated), True, angle

    def _to_result(
        self,
        image,
        *,
        rotation: float,
        perspective: bool,
        used_original: bool,
        failure: str | None = None,
    ) -> GeometryNormalizeResult:
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        w, h = image.size
        return GeometryNormalizeResult(
            image_bytes=buf.getvalue(),
            width=int(w),
            height=int(h),
            applied_rotation_deg=float(rotation),
            perspective_corrected=bool(perspective),
            used_original_region=bool(used_original),
            failure_reason=failure,
        )


__all__ = [
    "GeometryNormalizeResult",
    "LabelGeometryNormalizer",
    "NormalizedLabelImage",
    "validate_normalized_polygon",
]
