"""
Storage path convention for inventory visual references — v3.2.4.

Logical path: inventories/{inventory_id}/visual_references/{reference_id}.{ext}
Extension is derived from mime_type; original filename is not used as storage key.
"""

from __future__ import annotations

# Allowed image types and extension mapping (plan: jpg, jpeg, png, webp)
_MIME_TO_EXT: dict[str, str] = {
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}

DEFAULT_EXT = "bin"


def extension_from_mime_type(mime_type: str) -> str:
    """Return file extension for storage path. Defaults to 'bin' for unknown types."""
    if not mime_type or not mime_type.strip():
        return DEFAULT_EXT
    normalized = mime_type.strip().lower().split(";")[0].strip()
    return _MIME_TO_EXT.get(normalized, DEFAULT_EXT)


def visual_reference_storage_path(
    inventory_id: str,
    reference_id: str,
    mime_type: str,
) -> str:
    """
    Build the relative storage path for a visual reference file.

    Format: inventories/{inventory_id}/visual_references/{reference_id}.{ext}
    Does not use original filename; extension comes from mime_type.
    """
    ext = extension_from_mime_type(mime_type)
    return f"inventories/{inventory_id}/visual_references/{reference_id}.{ext}"
