"""Tests for shared reference image MIME helpers (supplier uploads)."""

from __future__ import annotations

import pytest

from src.application.utils.reference_image_mime import (
    ALLOWED_MIME_TYPES,
    extension_from_mime_type,
    normalize_reference_image_mime,
)


def test_normalize_reference_image_mime_strips_parameters() -> None:
    assert normalize_reference_image_mime("IMAGE/JPEG; charset=utf-8") == "image/jpeg"


@pytest.mark.parametrize(
    "mime,expected",
    [
        ("image/jpeg", "jpg"),
        ("image/jpg", "jpg"),
        ("image/png", "png"),
        ("image/webp", "webp"),
        ("", "bin"),
        ("application/octet-stream", "bin"),
    ],
)
def test_extension_from_mime_type(mime: str, expected: str) -> None:
    assert extension_from_mime_type(mime) == expected


def test_allowed_mime_types_contains_common_images() -> None:
    assert "image/jpeg" in ALLOWED_MIME_TYPES
    assert "image/png" in ALLOWED_MIME_TYPES
