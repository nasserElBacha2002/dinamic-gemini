"""HEIC/HEIF detection and aisle asset list helpers (shared by preview/file routing logic).

Suffixes align with :func:`src.api.routes.v3.shared.heic_extensions` (``.heic``, ``.heif``).
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from src.domain.assets.entities import SourceAsset

# Match ``shared._HEIC_EXTENSIONS`` — kept here so application does not import API routes.
HEIC_FILENAME_SUFFIXES: tuple[str, ...] = (".heic", ".heif")
_HEIC_MIME_TYPES = frozenset({"image/heic", "image/heif"})


def select_source_asset_by_id(
    assets: Sequence[SourceAsset],
    asset_id: str,
) -> SourceAsset | None:
    """Return the asset with matching ``id``, or ``None``."""
    for a in assets:
        if a.id == asset_id:
            return a
    return None


def source_asset_is_heic(asset: SourceAsset) -> bool:
    """True when MIME type or filename/storage suffix indicates HEIC/HEIF."""
    mt = (asset.mime_type or "").lower()
    if mt in _HEIC_MIME_TYPES:
        return True
    if Path(asset.storage_path or "").suffix.lower() in HEIC_FILENAME_SUFFIXES:
        return True
    if Path(asset.original_filename or "").suffix.lower() in HEIC_FILENAME_SUFFIXES:
        return True
    return False
