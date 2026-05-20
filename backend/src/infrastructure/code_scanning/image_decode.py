"""Decode uploaded source asset bytes to RGB PIL images for pyzbar."""

from __future__ import annotations

import io
import logging
from pathlib import Path

from PIL import Image

from src.application.services.source_asset_heic import HEIC_FILENAME_SUFFIXES, source_asset_is_heic

logger = logging.getLogger(__name__)

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


class UnsupportedImageFormatError(ValueError):
    """Raised when asset MIME/filename is not a supported still image."""


def is_supported_image_asset(asset) -> bool:
    if getattr(asset, "type", None) is not None and str(getattr(asset.type, "value", asset.type)) != "photo":
        return False
    mt = (getattr(asset, "mime_type", None) or getattr(asset, "content_type", None) or "").lower()
    if mt in _SUPPORTED_MIME_EXACT:
        return True
    if any(mt.startswith(p) for p in _SUPPORTED_MIME_PREFIXES):
        return True
    for hint in (
        getattr(asset, "original_filename", "") or "",
        getattr(asset, "storage_path", "") or "",
    ):
        if Path(hint).suffix.lower() in HEIC_FILENAME_SUFFIXES:
            return True
    return source_asset_is_heic(asset)


def decode_bytes_to_rgb_image(
    raw: bytes,
    *,
    asset_id: str = "",
    asset=None,
) -> Image.Image:
    """Decode image bytes to RGB ``PIL.Image`` for barcode scanning."""
    if not raw:
        raise ValueError(f"empty image bytes for asset {asset_id}")
    aid = asset_id or (getattr(asset, "id", None) or "")
    if asset is not None and source_asset_is_heic(asset):
        return _decode_heic_bytes(raw)
    try:
        img = Image.open(io.BytesIO(raw))
        return img.convert("RGB")
    except Exception as exc:
        if _bytes_look_like_heic(raw):
            try:
                return _decode_heic_bytes(raw)
            except Exception:
                pass
        raise ValueError(f"cannot decode image bytes for asset {aid}") from exc


def _bytes_look_like_heic(raw: bytes) -> bool:
    return len(raw) >= 12 and raw[4:8] == b"ftyp"


def _decode_heic_bytes(raw: bytes) -> Image.Image:
    try:
        import pillow_heif
    except ImportError as exc:
        raise ValueError("HEIC decode requires pillow-heif") from exc
    pillow_heif.register_heif_opener()
    return Image.open(io.BytesIO(raw)).convert("RGB")
