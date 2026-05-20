"""Tests for image decode helpers and supported-asset detection."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.domain.assets.entities import SourceAsset, SourceAssetType
from src.infrastructure.code_scanning.image_decode import (
    UnreadableImageError,
    UnsupportedImageFormatError,
    decode_bytes_to_rgb_image,
    is_supported_image_asset,
)


def _photo(
    asset_id: str,
    *,
    mime_type: str | None = None,
    filename: str = "photo.jpg",
    storage_key: str | None = None,
    asset_type: SourceAssetType = SourceAssetType.PHOTO,
) -> SourceAsset:
    now = datetime(2026, 5, 20, tzinfo=timezone.utc)
    return SourceAsset(
        id=asset_id,
        aisle_id="aisle-1",
        type=asset_type,
        original_filename=filename,
        storage_path=f"uploads/{filename}",
        storage_key=storage_key or f"uploads/{filename}",
        mime_type=mime_type,
        uploaded_at=now,
    )


@pytest.mark.parametrize(
    "filename",
    ["photo.jpg", "photo.jpeg", "photo.png", "photo.webp", "photo.heic", "photo.heif"],
)
def test_missing_mime_supported_by_extension(filename: str) -> None:
    asset = _photo("a1", mime_type=None, filename=filename)
    assert is_supported_image_asset(asset) is True


def test_video_asset_unsupported() -> None:
    asset = _photo("v1", asset_type=SourceAssetType.VIDEO, filename="clip.mp4")
    assert is_supported_image_asset(asset) is False


def test_unknown_extension_unsupported() -> None:
    asset = _photo("a1", mime_type=None, filename="data.bin")
    assert is_supported_image_asset(asset) is False


def test_empty_bytes_raises_unreadable() -> None:
    with pytest.raises(UnreadableImageError, match="empty image bytes"):
        decode_bytes_to_rgb_image(b"")


def test_corrupt_bytes_raises_unreadable() -> None:
    asset = _photo("a1")
    with pytest.raises(UnreadableImageError):
        decode_bytes_to_rgb_image(b"not-an-image", asset=asset)


def test_unsupported_image_format_error_is_value_error() -> None:
    assert issubclass(UnsupportedImageFormatError, ValueError)
