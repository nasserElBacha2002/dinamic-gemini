"""
Unit tests for SqlSourceAssetRepository — timestamp guard and behavior.

Does not require a real DB; uses mocks to assert save() validates uploaded_at before SQL.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from src.domain.assets.entities import SourceAsset, SourceAssetType
from src.infrastructure.repositories.sql_source_asset_repository import (
    SqlSourceAssetRepository,
)


def test_save_raises_when_uploaded_at_is_none() -> None:
    """uploaded_at is required; raise before any SQL execution."""
    client = MagicMock()
    repo = SqlSourceAssetRepository(client)
    asset = SourceAsset(
        id="asset-1",
        aisle_id="aisle-1",
        type=SourceAssetType.PHOTO,
        original_filename="f.jpg",
        storage_path="aisles/aisle-1/raw/asset-1_f.jpg",
        mime_type="image/jpeg",
        uploaded_at=None,  # type: ignore[arg-type]
    )
    with pytest.raises(ValueError, match="uploaded_at is required"):
        repo.save(asset)
    client.cursor.assert_not_called()
