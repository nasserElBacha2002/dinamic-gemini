"""Decode uploaded source asset bytes to RGB PIL images for pyzbar."""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageOps

from src.application.services.source_asset_heic import HEIC_FILENAME_SUFFIXES, source_asset_is_heic
from src.domain.assets.entities import SourceAsset, SourceAssetType

_SUPPORTED_MIME_PREFIXES = ("image/jpeg", "image/png", "image/webp")
_SUPPORTED_MIME_EXACT = frozenset(
    {
        "image/jpeg",
        "image/jpg",
        "image/png",
        "image/webp",
        "image/heic",
        "image/heif",
    }
)
_SUPPORTED_IMAGE_SUFFIXES = frozenset(
    {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"} | set(HEIC_FILENAME_SUFFIXES)
)


class UnsupportedImageFormatError(ValueError):
    """Raised when MIME/extension is not a supported still image."""


class UnreadableImageError(ValueError):
    """Raised when bytes cannot be decoded as an image."""


def _filename_suffix_from_asset(asset: SourceAsset) -> str:
    for hint in (
        asset.original_filename or "",
        asset.storage_path or "",
        asset.storage_key or "",
    ):
        suffix = Path(hint).suffix.lower()
        if suffix:
            return suffix
    return ""


def is_supported_image_asset(asset: SourceAsset) -> bool:
    if asset.type == SourceAssetType.VIDEO:
        return False
    if asset.type != SourceAssetType.PHOTO:
        return False
    mt = (asset.mime_type or "").lower()
    if mt in _SUPPORTED_MIME_EXACT:
        return True
    if any(mt.startswith(p) for p in _SUPPORTED_MIME_PREFIXES):
        return True
    suffix = _filename_suffix_from_asset(asset)
    if suffix in _SUPPORTED_IMAGE_SUFFIXES:
        return True
    return source_asset_is_heic(asset)


def decode_bytes_to_rgb_image(
    raw: bytes,
    *,
    asset_id: str = "",
    asset: SourceAsset | None = None,
) -> Image.Image:
    """Decode image bytes to RGB ``PIL.Image`` for barcode scanning."""
    if not raw:
        aid = asset_id or (getattr(asset, "id", None) or "")
        raise UnreadableImageError(f"empty image bytes for asset {aid}")
    aid = asset_id or (getattr(asset, "id", None) or "")
    if asset is not None and source_asset_is_heic(asset):
        try:
            return _decode_heic_bytes(raw)
        except Exception as exc:
            raise UnreadableImageError(f"cannot decode HEIC image for asset {aid}") from exc
    try:
        img = Image.open(io.BytesIO(raw))
        return _to_oriented_rgb(img)
    except Exception as exc:
        if _bytes_look_like_heic(raw):
            try:
                return _decode_heic_bytes(raw)
            except Exception as heic_exc:
                raise UnreadableImageError(
                    f"cannot decode HEIC image for asset {aid}"
                ) from heic_exc
        raise UnreadableImageError(f"cannot decode image bytes for asset {aid}") from exc


def _to_oriented_rgb(img: Image.Image) -> Image.Image:
    """Apply EXIF orientation then convert to RGB.

    Barcode/QR decoding is orientation-sensitive; phones commonly store a rotated sensor
    image plus an EXIF orientation tag. ``ImageOps.exif_transpose`` bakes that rotation in
    so pyzbar sees the upright image. Images without EXIF orientation are returned unchanged
    (exif_transpose is a no-op), so JPEG/PNG/WebP without the tag keep prior behavior.
    """
    try:
        transposed = ImageOps.exif_transpose(img)
    except Exception:
        transposed = img
    return (transposed or img).convert("RGB")


def _bytes_look_like_heic(raw: bytes) -> bool:
    return len(raw) >= 12 and raw[4:8] == b"ftyp"


def _decode_heic_bytes(raw: bytes) -> Image.Image:
    try:
        import pillow_heif
    except ImportError as exc:
        raise UnreadableImageError("HEIC decode requires pillow-heif") from exc
    pillow_heif.register_heif_opener()
    return _to_oriented_rgb(Image.open(io.BytesIO(raw)))
