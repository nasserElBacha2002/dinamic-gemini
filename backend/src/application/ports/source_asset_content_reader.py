"""Port for loading source asset bytes from artifact storage (code scan Phase 2)."""

from __future__ import annotations

from typing import Protocol

from src.domain.assets.entities import SourceAsset


class SourceAssetContentReader(Protocol):
    def read_image_bytes(self, asset: SourceAsset) -> bytes:
        """Load raw bytes for a source asset using canonical storage metadata.

        Raises:
            ValueError: Missing storage key or empty payload.
            FileNotFoundError: Object not found in storage.
        """
