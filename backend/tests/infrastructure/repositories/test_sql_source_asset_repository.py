"""
Unit tests for SqlSourceAssetRepository — timestamp guard and behavior.

Does not require a real DB; uses mocks to assert save() validates uploaded_at before SQL.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.domain.assets.entities import SourceAsset, SourceAssetType
from src.infrastructure.repositories.sql_source_asset_repository import (
    SqlSourceAssetRepository,
    _row_to_asset,
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


def test_row_to_asset_prefers_provider_storage_key_when_present() -> None:
    row = SimpleNamespace(
        id="asset-1",
        aisle_id="aisle-1",
        type="photo",
        original_filename="img.jpg",
        storage_path="aisles/aisle-1/raw/legacy.jpg",
        storage_provider="s3",
        storage_bucket="bucket-a",
        storage_key="uploads/aisles/aisle-1/raw/object.jpg",
        content_type="image/jpeg",
        file_size_bytes=1234,
        etag="abc123",
        mime_type="image/jpeg",
        uploaded_at=datetime.now(timezone.utc),
        metadata_json=None,
    )
    asset = _row_to_asset(row)
    assert asset.storage_path == "aisles/aisle-1/raw/legacy.jpg"
    assert asset.storage_key == "uploads/aisles/aisle-1/raw/object.jpg"
    assert asset.storage_provider == "s3"
    assert asset.storage_bucket == "bucket-a"
    assert asset.content_type == "image/jpeg"
    assert asset.file_size_bytes == 1234
    assert asset.etag == "abc123"


def test_row_to_asset_falls_back_to_legacy_storage_path() -> None:
    row = SimpleNamespace(
        id="asset-1",
        aisle_id="aisle-1",
        type="photo",
        original_filename="img.jpg",
        storage_path="aisles/aisle-1/raw/legacy.jpg",
        storage_provider=None,
        storage_bucket=None,
        storage_key=None,
        content_type=None,
        file_size_bytes=None,
        etag=None,
        mime_type="image/jpeg",
        uploaded_at=datetime.now(timezone.utc),
        metadata_json=None,
    )
    asset = _row_to_asset(row)
    assert asset.storage_key == "aisles/aisle-1/raw/legacy.jpg"
    assert asset.content_type == "image/jpeg"
