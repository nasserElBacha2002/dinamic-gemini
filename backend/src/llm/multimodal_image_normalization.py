"""Shared multimodal image normalization for all LLM providers and image roles.

Primary evidence and supplier visual references should be normalized once per
request (typically in the provider adapter) with a request-local cache.
Final Anthropic validation additionally inspects exact base64 bytes before the SDK.
"""

from __future__ import annotations

import hashlib
import io
import logging
from dataclasses import dataclass, field
from typing import Any, Literal

from PIL import Image, ImageOps

logger = logging.getLogger(__name__)

ImageRole = Literal["primary_evidence", "visual_reference", "context"]


class ProviderImageNormalizationError(ValueError):
    """Raised when an image cannot be safely prepared for a multimodal provider request."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "PROVIDER_IMAGE_NORMALIZATION_FAILED",
        source_id: str | None = None,
        role: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.source_id = source_id
        self.role = role


@dataclass(frozen=True)
class ProviderImagePolicy:
    """Provider-scoped limits applied before adapter SDK calls."""

    max_dimension: int
    jpeg_quality: int
    preferred_format: str = "JPEG"
    max_images_per_request: int | None = None


@dataclass(frozen=True)
class NormalizedImage:
    data: bytes
    mime_type: str
    width: int
    height: int
    original_width: int
    original_height: int
    was_resized: bool
    source_id: str | None
    role: str
    mime_type_before: str | None = None
    bytes_before: int | None = None


@dataclass
class MultimodalNormalizationContext:
    """Request/job-local normalize cache. Must not outlive one request build."""

    _cache: dict[str, NormalizedImage] = field(default_factory=dict, repr=False)
    normalize_work_count: int = 0

    def get(self, key: str) -> NormalizedImage | None:
        return self._cache.get(key)

    def put(self, key: str, value: NormalizedImage) -> None:
        self._cache[key] = value

    def clear(self) -> None:
        self._cache.clear()

    @property
    def size(self) -> int:
        return len(self._cache)


def provider_image_policy_for(
    provider: str,
    *,
    max_dimension: int,
    jpeg_quality: int,
) -> ProviderImagePolicy:
    """Build policy from resolved settings (caller supplies validated ints)."""
    p = (provider or "").strip().lower()
    return ProviderImagePolicy(
        max_dimension=max(1, int(max_dimension)),
        jpeg_quality=max(1, min(100, int(jpeg_quality))),
        preferred_format="JPEG",
        max_images_per_request=None if p != "claude" else None,
    )


def _cache_key(
    raw: bytes,
    *,
    policy: ProviderImagePolicy,
    source_id: str | None,
    role: str,
) -> str:
    digest = hashlib.sha256(raw).hexdigest()
    return (
        f"{digest}:{policy.max_dimension}:{policy.jpeg_quality}:"
        f"{policy.preferred_format}:{role}:{source_id or ''}"
    )


def _composite_rgba_onto_white(img: Image.Image) -> Image.Image:
    """Flatten alpha onto white (avoid black background when converting to JPEG)."""
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        background = Image.new("RGB", rgba.size, (255, 255, 255))
        background.paste(rgba, mask=rgba.split()[-1])
        return background
    if img.mode == "CMYK":
        return img.convert("RGB")
    if img.mode != "RGB":
        return img.convert("RGB")
    return img


def _open_and_transpose(image_bytes: bytes) -> Image.Image:
    if not image_bytes:
        raise ProviderImageNormalizationError(
            "empty image bytes",
            code="PROVIDER_IMAGE_NORMALIZATION_FAILED",
        )
    try:
        with Image.open(io.BytesIO(image_bytes)) as opened:
            # Load fully while handle is open; then work on a detached copy.
            transposed = ImageOps.exif_transpose(opened)
            img = transposed.copy() if transposed is not None else opened.copy()
    except Exception as exc:  # noqa: BLE001 — corrupt/unsupported image input
        raise ProviderImageNormalizationError(
            f"failed to open image: {exc}",
            code="PROVIDER_IMAGE_NORMALIZATION_FAILED",
        ) from exc
    return img


def normalize_multimodal_image(
    image_bytes: bytes,
    *,
    source_id: str | None,
    role: str,
    policy: ProviderImagePolicy,
    mime_type_hint: str | None = None,
    use_cache: bool = True,
    ctx: MultimodalNormalizationContext | None = None,
) -> NormalizedImage:
    """Normalize one image to provider policy (EXIF, resize, JPEG, validation)."""
    if policy.max_dimension < 256 or policy.max_dimension > 8192:
        raise ProviderImageNormalizationError(
            f"invalid max_dimension={policy.max_dimension}",
            code="PROVIDER_IMAGE_NORMALIZATION_FAILED",
            source_id=source_id,
            role=role,
        )
    if not (1 <= policy.jpeg_quality <= 100):
        raise ProviderImageNormalizationError(
            f"invalid jpeg_quality={policy.jpeg_quality}",
            code="PROVIDER_IMAGE_NORMALIZATION_FAILED",
            source_id=source_id,
            role=role,
        )

    key = _cache_key(image_bytes, policy=policy, source_id=source_id, role=role)
    if use_cache and ctx is not None:
        hit = ctx.get(key)
        if hit is not None:
            return hit

    bytes_before = len(image_bytes)
    img = _open_and_transpose(image_bytes)
    try:
        original_width, original_height = img.size
        if original_width <= 0 or original_height <= 0:
            raise ProviderImageNormalizationError(
                "non-positive image dimensions",
                code="PROVIDER_IMAGE_NORMALIZATION_FAILED",
                source_id=source_id,
                role=role,
            )

        longest = max(original_width, original_height)
        was_resized = longest > policy.max_dimension
        work = img
        if was_resized:
            scale = policy.max_dimension / float(longest)
            new_w = max(1, int(round(original_width * scale)))
            new_h = max(1, int(round(original_height * scale)))
            work = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

        rgb = _composite_rgba_onto_white(work)
        out_buf = io.BytesIO()
        # Drop EXIF by saving without exif= keyword.
        rgb.save(out_buf, format="JPEG", quality=policy.jpeg_quality, optimize=True)
        data = out_buf.getvalue()
        width, height = rgb.size
    finally:
        img.close()

    if not data:
        raise ProviderImageNormalizationError(
            "normalized image produced empty bytes",
            code="PROVIDER_IMAGE_NORMALIZATION_FAILED",
            source_id=source_id,
            role=role,
        )
    if max(width, height) > policy.max_dimension:
        raise ProviderImageNormalizationError(
            f"normalized dimensions {width}x{height} exceed max {policy.max_dimension}",
            code="PROVIDER_IMAGE_DIMENSION_EXCEEDED",
            source_id=source_id,
            role=role,
        )

    result = NormalizedImage(
        data=data,
        mime_type="image/jpeg",
        width=width,
        height=height,
        original_width=original_width,
        original_height=original_height,
        was_resized=was_resized,
        source_id=source_id,
        role=role,
        mime_type_before=mime_type_hint,
        bytes_before=bytes_before,
    )
    logger.info(
        "multimodal_image_normalized",
        extra={
            "event": "multimodal_image_normalized",
            "role": role,
            "source_id": source_id,
            "original_width": original_width,
            "original_height": original_height,
            "normalized_width": width,
            "normalized_height": height,
            "was_resized": was_resized,
            "mime_type_before": mime_type_hint,
            "mime_type_after": "image/jpeg",
            "bytes_before": bytes_before,
            "bytes_after": len(data),
            "max_dimension": policy.max_dimension,
        },
    )
    if use_cache and ctx is not None:
        ctx.put(key, result)
        ctx.normalize_work_count += 1
    elif ctx is not None:
        ctx.normalize_work_count += 1
    return result


def normalize_pil_image(
    image: Any,
    *,
    source_id: str | None,
    role: str,
    policy: ProviderImagePolicy,
    mime_type_hint: str | None = None,
    ctx: MultimodalNormalizationContext | None = None,
) -> NormalizedImage:
    """Normalize a PIL image via shared JPEG pipeline."""
    from PIL import Image as PILImage

    if not isinstance(image, PILImage.Image):
        raise ProviderImageNormalizationError(
            "expected PIL.Image.Image",
            code="PROVIDER_IMAGE_NORMALIZATION_FAILED",
            source_id=source_id,
            role=role,
        )
    buf = io.BytesIO()
    # Encode source as PNG to preserve alpha before shared flatten/JPEG path.
    src = image
    if src.mode not in ("RGB", "RGBA", "L", "LA", "P", "CMYK"):
        src = src.convert("RGBA")
    save_mode = src
    if save_mode.mode == "CMYK":
        save_mode = save_mode.convert("RGB")
        save_mode.save(buf, format="JPEG", quality=95)
    elif save_mode.mode in ("RGBA", "LA", "P"):
        save_mode.save(buf, format="PNG")
    else:
        save_mode.convert("RGB").save(buf, format="JPEG", quality=95)
    return normalize_multimodal_image(
        buf.getvalue(),
        source_id=source_id,
        role=role,
        policy=policy,
        mime_type_hint=mime_type_hint,
        ctx=ctx,
    )


def normalize_bgr_ndarray(
    arr: Any,
    *,
    source_id: str | None,
    role: str,
    policy: ProviderImagePolicy,
    ctx: MultimodalNormalizationContext | None = None,
) -> NormalizedImage:
    """Normalize OpenCV BGR ndarray via shared JPEG pipeline."""
    import cv2
    import numpy as np

    if arr is None or not isinstance(arr, np.ndarray) or arr.size == 0:
        raise ProviderImageNormalizationError(
            "empty frame",
            code="PROVIDER_IMAGE_NORMALIZATION_FAILED",
            source_id=source_id,
            role=role,
        )
    ok, buf = cv2.imencode(".png", arr)
    if not ok or buf is None:
        raise ProviderImageNormalizationError(
            "failed to encode BGR frame",
            code="PROVIDER_IMAGE_NORMALIZATION_FAILED",
            source_id=source_id,
            role=role,
        )
    return normalize_multimodal_image(
        buf.tobytes(),
        source_id=source_id,
        role=role,
        policy=policy,
        mime_type_hint="image/png",
        ctx=ctx,
    )


def clear_multimodal_normalize_cache() -> None:
    """Compatibility no-op: global cache removed; request-local contexts clear themselves."""


def log_multimodal_request_ready(
    *,
    provider: str,
    primary_count: int,
    reference_count: int,
    policy: ProviderImagePolicy,
    largest_width: int,
    largest_height: int,
    all_validated: bool,
    total_image_count: int | None = None,
) -> None:
    total = (
        total_image_count
        if total_image_count is not None
        else primary_count + reference_count
    )
    logger.info(
        "multimodal_request_ready",
        extra={
            "event": "multimodal_request_ready",
            "provider": provider,
            "primary_evidence_count": primary_count,
            "visual_reference_count": reference_count,
            "total_image_count": total,
            "max_dimension_allowed": policy.max_dimension,
            "largest_final_width": largest_width,
            "largest_final_height": largest_height,
            "all_images_validated": all_validated,
        },
    )
