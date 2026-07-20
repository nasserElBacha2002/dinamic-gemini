"""Phase 4 — configurable OCR image preprocessing variants.

Produces a bounded set of PreparedImage variants (never a combinatorial explosion).
Destructive transforms are optional; the original EXIF-oriented RGB is always variant 0
when decode succeeds.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass

from src.application.ports.internal_label_reader import PreparedImage

logger = logging.getLogger(__name__)

VARIANT_ORIGINAL = "original"
VARIANT_GRAY_CONTRAST = "gray_contrast"
VARIANT_ADAPTIVE_THRESHOLD = "adaptive_threshold"
VARIANT_DESKEW = "deskew"


@dataclass(frozen=True)
class OcrPreprocessConfig:
    max_image_dimension: int = 2048
    max_variants: int = 3
    enable_gray_contrast: bool = True
    enable_adaptive_threshold: bool = True
    enable_deskew: bool = False


class OcrImagePreprocessor:
    """Decode → EXIF orient → optional resize → emit up to ``max_variants`` prepared images."""

    def __init__(self, config: OcrPreprocessConfig) -> None:
        self._config = config

    def prepare_variants(self, content: bytes) -> list[PreparedImage]:
        """Yield prepared variants in priority order. Stops at ``max_variants``."""
        rgb = self._decode_oriented_rgb(content)
        if rgb is None:
            raise ValueError("OCR_IMAGE_DECODE_FAILED")

        rgb = self._maybe_downscale(rgb)
        variants: list[PreparedImage] = [self._to_prepared(rgb, VARIANT_ORIGINAL)]

        max_v = max(1, int(self._config.max_variants))
        if len(variants) >= max_v:
            return variants

        if self._config.enable_gray_contrast:
            gray = self._gray_contrast(rgb)
            if gray is not None:
                variants.append(self._to_prepared(gray, VARIANT_GRAY_CONTRAST))
            if len(variants) >= max_v:
                return variants

        if self._config.enable_adaptive_threshold:
            thr = self._adaptive_threshold(rgb)
            if thr is not None:
                variants.append(self._to_prepared(thr, VARIANT_ADAPTIVE_THRESHOLD))
            if len(variants) >= max_v:
                return variants

        if self._config.enable_deskew:
            deskewed = self._deskew(rgb)
            if deskewed is not None:
                variants.append(self._to_prepared(deskewed, VARIANT_DESKEW))

        return variants[:max_v]

    def _decode_oriented_rgb(self, content: bytes):
        try:
            from PIL import Image, ImageOps

            with Image.open(io.BytesIO(content)) as img:
                oriented = ImageOps.exif_transpose(img) or img
                return oriented.convert("RGB")
        except Exception:
            logger.warning("ocr.preprocess.decode_failed", exc_info=True)
            return None

    def _maybe_downscale(self, image):
        max_side = int(self._config.max_image_dimension or 0)
        if max_side <= 0:
            return image
        longest = max(image.size)
        if longest <= max_side:
            return image
        scale = max_side / float(longest)
        new_size = (max(1, int(image.size[0] * scale)), max(1, int(image.size[1] * scale)))
        return image.resize(new_size)

    def _to_prepared(self, image, variant_name: str) -> PreparedImage:
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        w, h = image.size
        return PreparedImage(
            content=buf.getvalue(),
            width=int(w),
            height=int(h),
            variant_name=variant_name,
            mime_type="image/png",
        )

    def _gray_contrast(self, rgb):
        try:
            from PIL import ImageEnhance, ImageOps

            gray = ImageOps.grayscale(rgb)
            return ImageEnhance.Contrast(gray).enhance(1.8).convert("RGB")
        except Exception:
            return None

    def _adaptive_threshold(self, rgb):
        try:
            import cv2
            import numpy as np

            arr = np.array(rgb.convert("L"))
            blurred = cv2.GaussianBlur(arr, (5, 5), 0)
            thr = cv2.adaptiveThreshold(
                blurred,
                255,
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY,
                31,
                10,
            )
            from PIL import Image

            return Image.fromarray(thr).convert("RGB")
        except Exception:
            return None

    def _deskew(self, rgb):
        """Light deskew via OpenCV minAreaRect on thresholded ink; skip if angle ~0."""
        try:
            import cv2
            import numpy as np
            from PIL import Image

            arr = np.array(rgb.convert("L"))
            _, thr = cv2.threshold(arr, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
            coords = np.column_stack(np.where(thr > 0))
            if coords.size == 0:
                return None
            angle = cv2.minAreaRect(coords)[-1]
            if angle < -45:
                angle = -(90 + angle)
            else:
                angle = -angle
            if abs(angle) < 0.5 or abs(angle) > 15:
                return None
            (h, w) = arr.shape[:2]
            matrix = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1.0)
            rotated = cv2.warpAffine(
                np.array(rgb),
                matrix,
                (w, h),
                flags=cv2.INTER_CUBIC,
                borderMode=cv2.BORDER_REPLICATE,
            )
            return Image.fromarray(rotated)
        except Exception:
            return None


__all__ = [
    "OcrImagePreprocessor",
    "OcrPreprocessConfig",
    "VARIANT_ADAPTIVE_THRESHOLD",
    "VARIANT_DESKEW",
    "VARIANT_GRAY_CONTRAST",
    "VARIANT_ORIGINAL",
]
