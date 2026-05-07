"""Shared MIME and extension rules for reference image uploads (supplier + legacy paths removed in C9)."""

from __future__ import annotations

ALLOWED_MIME_TYPES: frozenset[str] = frozenset(
    {
        "image/jpeg",
        "image/jpg",
        "image/png",
        "image/webp",
    }
)

# Allowed image types and extension mapping (jpg, jpeg, png, webp)
_MIME_TO_EXT: dict[str, str] = {
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}

DEFAULT_EXT = "bin"


def normalize_reference_image_mime(mime: str) -> str:
    """Normalize Content-Type for comparisons (lowercase, strip parameters)."""
    raw = (mime or "").strip().lower()
    return raw.split(";", 1)[0].strip()


def extension_from_mime_type(mime_type: str) -> str:
    """Return file extension for storage paths. Defaults to 'bin' for unknown types."""
    if not mime_type or not mime_type.strip():
        return DEFAULT_EXT
    normalized = mime_type.strip().lower().split(";")[0].strip()
    return _MIME_TO_EXT.get(normalized, DEFAULT_EXT)
